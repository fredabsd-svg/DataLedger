"""DL-089 (BL-72), migração 0026: aditiva, reversível, e a reversão RECUSA com origem automática.

Critérios do plano cobertos:

1. Os lançamentos que já existem ficam `manual` (o default da coluna resolve, sem UPDATE em
   linha protegida).
7. Migração ida/volta/ida, com a recusa de reversão quando há lançamento de origem automática.

PostgreSQL-only: o gatilho e a função de imutabilidade só existem lá. Dados sintéticos. Os
testes são `transaction=True` porque mudam o schema e precisam voltar ao estado mais recente.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.contabilidade.models import OrigemLancamento, TipoDocumentoOrigem, TipoPartida
from apps.contabilidade.services import criar_lancamento
from apps.contabilidade.tests.cenario_dl077_exportacao import (
    CNPJ_DA_EMPRESA,
    criar_empresa,
    criar_escritorio,
    criar_plano,
)

ANTERIOR = [("contabilidade", "0025_dl077_correcao_auditoria_rodada_1")]
ATUAL = [("contabilidade", "0026_dl089_origem_do_lancamento")]
TABELA = "contabilidade_lancamentocontabil"

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(
        connection.vendor != "postgresql",
        reason="A função e o gatilho de origem existem só em PostgreSQL (DL-089, 0026).",
    ),
]


def _migrar(alvo):
    MigrationExecutor(connection).migrate(alvo)


def _aplicadas():
    return MigrationExecutor(connection).loader.applied_migrations


def _colunas():
    with connection.cursor() as cursor:
        return {c.name for c in connection.introspection.get_table_description(cursor, TABELA)}


def _corpo_da_funcao():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_get_functiondef('contabilidade_recusar_alteracao_do_livro'::regproc)"
        )
        return cursor.fetchone()[0]


def _origem_no_banco(lancamento_id):
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT origem FROM {TABELA} WHERE id = %s", [lancamento_id])
        return cursor.fetchone()[0]


@pytest.fixture
def cenario():
    escritorio = criar_escritorio("Escritório DL-089 migração", "89898000000189")
    empresa = criar_empresa(
        escritorio=escritorio, razao_social="Empresa DL-089 Migração Ltda", cnpj=CNPJ_DA_EMPRESA
    )
    contas = criar_plano(empresa)
    return {"empresa": empresa, "contas": contas}


def _lancar(cenario, **extra):
    contas = cenario["contas"]
    return criar_lancamento(
        empresa=cenario["empresa"],
        data=date(2026, 3, 10),
        historico="Lançamento de migração (sintético)",
        itens=[
            {"conta": contas["1.1.1"], "tipo": TipoPartida.DEBITO, "valor": Decimal("25.00")},
            {"conta": contas["5.1"], "tipo": TipoPartida.CREDITO, "valor": Decimal("25.00")},
        ],
        **extra,
    )


def test_ida_volta_ida_mantem_lancamento_manual_como_manual(cenario):
    manual = _lancar(cenario)
    assert "origem" in _colunas()

    try:
        _migrar(ANTERIOR)
        assert "origem" not in _colunas()
        assert "lancamento_origem_imutavel" not in _corpo_da_funcao()
        # A linha continua lá: a reversão só tira colunas, nunca apaga lançamento.
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) FROM {TABELA} WHERE id = %s", [manual.pk])
            assert cursor.fetchone()[0] == 1
    finally:
        _migrar(ATUAL)

    assert "origem" in _colunas()
    assert _origem_no_banco(manual.pk) == OrigemLancamento.MANUAL
    # A função volta com a regra nova, e o gatilho segue recusando a alteração de origem.
    assert "lancamento_origem_imutavel" in _corpo_da_funcao()


def test_reversao_recusa_com_mensagem_se_houver_lancamento_de_origem_automatica(cenario):
    automatico = _lancar(
        cenario,
        origem=OrigemLancamento.IMPORTACAO,
        documento_origem=(TipoDocumentoOrigem.IMPORTACAO_LANCAMENTOS, 1),
    )

    with pytest.raises(RuntimeError, match="DL-089: a migração 0026 não pode ser revertida"):
        _migrar(ANTERIOR)

    # Recusa = nada muda: o schema continua na 0026, a coluna e a origem continuam lá.
    assert ("contabilidade", "0026_dl089_origem_do_lancamento") in _aplicadas()
    assert "origem" in _colunas()
    assert _origem_no_banco(automatico.pk) == OrigemLancamento.IMPORTACAO
    assert "lancamento_origem_imutavel" in _corpo_da_funcao()


def test_reversao_recusa_tambem_lancamento_de_escrita_fiscal_reservada(cenario):
    _lancar(
        cenario,
        origem=OrigemLancamento.ESCRITA_FISCAL,
        documento_origem=(TipoDocumentoOrigem.ESCRITURACAO_NFE, "123"),
    )

    with pytest.raises(RuntimeError, match="origem automática"):
        _migrar(ANTERIOR)

    assert ("contabilidade", "0026_dl089_origem_do_lancamento") in _aplicadas()
