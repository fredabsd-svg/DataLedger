"""DL-089, correção da rodada 1 da auditoria: invariantes de origem que o banco precisa garantir.

- A3/T1: INSERT por SQL que não informa `origem` grava `manual` (o `db_default`). É o que
  sustenta a restauração de backup anterior à 0026 (`pg_restore --data-only`).
- A3/T2: o backfill da competência (a única exceção do gatilho de imutabilidade) NÃO pode
  carregar troca de origem ou de documento na mesma atualização.
- A3/T3: identificador vazio, ou com espaço nas pontas, é recusado pela CHECK.
- A6: origem e tipo de documento pareados, também por SQL direto.

PostgreSQL-only: o gatilho, a função e as CHECKs de nome só existem lá. Dados sintéticos. Cada
teste roda numa transação do pytest, que é desfeita ao fim.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.db import DatabaseError, IntegrityError, connection, transaction

from apps.contabilidade.models import (
    LancamentoContabil,
    OrigemLancamento,
    TipoDocumentoOrigem,
    TipoPartida,
)
from apps.contabilidade.services import criar_lancamento
from apps.contabilidade.tests.cenario_dl077_exportacao import (
    CNPJ_DA_EMPRESA,
    criar_empresa,
    criar_escritorio,
    criar_plano,
)
from apps.contabilidade.tests.gatilhos_do_livro import IMUTAVEL_LANCAMENTO, gatilho_desligado

TABELA = "contabilidade_lancamentocontabil"
TABELA_ITEM = "contabilidade_itemlancamento"

so_postgresql = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="O gatilho, a função e as CHECKs de nome de origem existem só em PostgreSQL (DL-089).",
)
pytestmark = [pytest.mark.django_db, so_postgresql]


@pytest.fixture
def cenario():
    escritorio = criar_escritorio("Escritório DL-089 banco", "89898000000189")
    empresa = criar_empresa(
        escritorio=escritorio, razao_social="Empresa DL-089 Banco Ltda", cnpj=CNPJ_DA_EMPRESA
    )
    return {"empresa": empresa, "contas": criar_plano(empresa)}


def _nome_da_restricao(erro):
    return erro.value.__cause__.diag.constraint_name


def _inserir_lancamento_por_sql(empresa_id, **colunas):
    """INSERT direto, só com as colunas informadas (as demais seguem o default do banco)."""
    colunas = {
        "empresa_id": empresa_id,
        "data": date(2026, 3, 10),
        "historico": "SQL (sintético)",
        **colunas,
    }
    nomes = ", ".join(colunas)
    marcadores = ", ".join(["%s"] * len(colunas))
    with connection.cursor() as cursor:
        cursor.execute(
            f"INSERT INTO {TABELA} ({nomes}, criado_em) VALUES ({marcadores}, NOW()) RETURNING id",
            list(colunas.values()),
        )
        return cursor.fetchone()[0]


def _inserir_item_por_sql(lancamento_id, conta_id, tipo, valor):
    with connection.cursor() as cursor:
        cursor.execute(
            f"INSERT INTO {TABELA_ITEM} (lancamento_id, conta_id, tipo, valor) "
            "VALUES (%s, %s, %s, %s)",
            [lancamento_id, conta_id, tipo, valor],
        )


def _lancamento_balanceado_por_sql(cenario, **colunas):
    """Lançamento com duas partidas iguais, gravado por SQL. Sem partidas, o Django recusa
    o teste no fim pela checagem de débito = crédito (adiada), e o teste não mede o que quer."""
    contas = cenario["contas"]
    lancamento_id = _inserir_lancamento_por_sql(cenario["empresa"].pk, **colunas)
    _inserir_item_por_sql(lancamento_id, contas["1.1.1"].pk, TipoPartida.DEBITO, Decimal("10.00"))
    _inserir_item_por_sql(lancamento_id, contas["5.1"].pk, TipoPartida.CREDITO, Decimal("10.00"))
    return lancamento_id


def _linha_do_lancamento(lancamento_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT origem, documento_origem_tipo, documento_origem_id "
            f"FROM {TABELA} WHERE id = %s",
            [lancamento_id],
        )
        return cursor.fetchone()


# ---------------------------------------------------------------------------
# A3/T1 — db_default: INSERT por SQL sem `origem` grava `manual`
# ---------------------------------------------------------------------------


def test_t1_insert_por_sql_sem_origem_grava_manual_e_sem_documento(cenario):
    empresa = cenario["empresa"]
    contas = cenario["contas"]

    with transaction.atomic():
        lancamento_id = _inserir_lancamento_por_sql(empresa.pk)
        _inserir_item_por_sql(
            lancamento_id, contas["1.1.1"].pk, TipoPartida.DEBITO, Decimal("10.00")
        )
        _inserir_item_por_sql(
            lancamento_id, contas["5.1"].pk, TipoPartida.CREDITO, Decimal("10.00")
        )

        assert _linha_do_lancamento(lancamento_id) == (OrigemLancamento.MANUAL, None, None)


# ---------------------------------------------------------------------------
# A3/T2 — o backfill da competência não carrega troca de origem nem de documento
# ---------------------------------------------------------------------------


@pytest.fixture
def lancamento_importado_sem_competencia(cenario):
    contas = cenario["contas"]
    lancamento = criar_lancamento(
        empresa=cenario["empresa"],
        data=date(2026, 3, 10),
        historico="Importado para backfill (sintético)",
        itens=[
            {"conta": contas["1.1.1"], "tipo": TipoPartida.DEBITO, "valor": Decimal("100.00")},
            {"conta": contas["5.1"], "tipo": TipoPartida.CREDITO, "valor": Decimal("100.00")},
        ],
        origem=OrigemLancamento.IMPORTACAO,
        documento_origem=(TipoDocumentoOrigem.IMPORTACAO_LANCAMENTOS, 1),
    )
    competencia = lancamento.competencia
    # Estado que o backfill encontra: lançamento anterior à DL-016 F5, sem competência.
    with gatilho_desligado(IMUTAVEL_LANCAMENTO):
        LancamentoContabil.objects.filter(pk=lancamento.pk).update(competencia=None)
    return {"lancamento": lancamento, "competencia": competencia}


def test_t2_backfill_puro_da_competencia_continua_aceito(lancamento_importado_sem_competencia):
    """Controle positivo: a exceção do backfill existe e segue valendo para a competência."""
    lancamento = lancamento_importado_sem_competencia["lancamento"]
    competencia = lancamento_importado_sem_competencia["competencia"]

    atualizados = LancamentoContabil.objects.filter(pk=lancamento.pk).update(
        competencia=competencia
    )

    assert atualizados == 1
    lancamento.refresh_from_db()
    assert lancamento.competencia_id == competencia.pk
    assert lancamento.origem == OrigemLancamento.IMPORTACAO


def test_t2_backfill_combinado_com_troca_de_origem_e_recusado(lancamento_importado_sem_competencia):
    lancamento = lancamento_importado_sem_competencia["lancamento"]
    competencia = lancamento_importado_sem_competencia["competencia"]

    with pytest.raises(DatabaseError) as erro:
        with transaction.atomic():
            LancamentoContabil.objects.filter(pk=lancamento.pk).update(
                competencia=competencia, origem=OrigemLancamento.MANUAL
            )

    assert _nome_da_restricao(erro) == "lancamento_origem_imutavel"


def test_t2_backfill_combinado_com_troca_de_documento_e_recusado(
    lancamento_importado_sem_competencia,
):
    lancamento = lancamento_importado_sem_competencia["lancamento"]
    competencia = lancamento_importado_sem_competencia["competencia"]

    with pytest.raises(DatabaseError) as erro:
        with transaction.atomic():
            LancamentoContabil.objects.filter(pk=lancamento.pk).update(
                competencia=competencia, documento_origem_id="999"
            )

    assert _nome_da_restricao(erro) == "lancamento_origem_imutavel"


# ---------------------------------------------------------------------------
# A3/T3 e A6 — identificador e pareamento, recusados pela CHECK
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("identificador", ["", "   ", " 12", "12 "])
def test_t3_identificador_vazio_ou_com_espaco_nas_pontas_e_recusado_pela_check(
    cenario, identificador
):
    with pytest.raises(IntegrityError) as erro:
        with transaction.atomic():
            _inserir_lancamento_por_sql(
                cenario["empresa"].pk,
                origem=OrigemLancamento.IMPORTACAO,
                documento_origem_tipo=TipoDocumentoOrigem.IMPORTACAO_LANCAMENTOS,
                documento_origem_id=identificador,
            )

    assert _nome_da_restricao(erro) == "ck_lancamentocontabil_documento_consistente"


def test_t3_identificador_valido_passa_pela_check(cenario):
    """Controle positivo: sem o espaço, o mesmo INSERT passa."""
    lancamento_id = _lancamento_balanceado_por_sql(
        cenario,
        origem=OrigemLancamento.IMPORTACAO,
        documento_origem_tipo=TipoDocumentoOrigem.IMPORTACAO_LANCAMENTOS,
        documento_origem_id="12",
    )

    assert _linha_do_lancamento(lancamento_id) == (
        OrigemLancamento.IMPORTACAO,
        TipoDocumentoOrigem.IMPORTACAO_LANCAMENTOS,
        "12",
    )


@pytest.mark.parametrize(
    "origem, tipo",
    [
        (OrigemLancamento.IMPORTACAO, TipoDocumentoOrigem.ESCRITURACAO_NFE),
        (OrigemLancamento.IMPORTACAO, TipoDocumentoOrigem.ESCRITURACAO_NFSE),
        (OrigemLancamento.ESCRITA_FISCAL, TipoDocumentoOrigem.IMPORTACAO_LANCAMENTOS),
    ],
)
def test_a6_par_origem_tipo_incoerente_e_recusado_pela_check(cenario, origem, tipo):
    with pytest.raises(IntegrityError) as erro:
        with transaction.atomic():
            _inserir_lancamento_por_sql(
                cenario["empresa"].pk,
                origem=origem,
                documento_origem_tipo=tipo,
                documento_origem_id="1",
            )

    assert _nome_da_restricao(erro) == "ck_lancamentocontabil_origem_pareada_ao_documento"


@pytest.mark.parametrize(
    "origem, tipo",
    [
        (OrigemLancamento.IMPORTACAO, TipoDocumentoOrigem.IMPORTACAO_LANCAMENTOS),
        (OrigemLancamento.ESCRITA_FISCAL, TipoDocumentoOrigem.ESCRITURACAO_NFE),
        (OrigemLancamento.ESCRITA_FISCAL, TipoDocumentoOrigem.ESCRITURACAO_NFSE),
    ],
)
def test_a6_par_origem_tipo_coerente_passa_pela_check(cenario, origem, tipo):
    """Controle positivo: os três pares que a tabela admite são gravados."""
    lancamento_id = _lancamento_balanceado_por_sql(
        cenario,
        origem=origem,
        documento_origem_tipo=tipo,
        documento_origem_id="1",
    )

    assert _linha_do_lancamento(lancamento_id) == (origem, tipo, "1")
