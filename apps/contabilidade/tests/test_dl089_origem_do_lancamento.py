"""DL-089 (BL-72) — origem e documento de origem do lançamento contábil.

Critérios do plano cobertos aqui (números do plano):

1. Os caminhos atuais gravam a origem certa: `criar_lancamento` sem origem grava `manual`;
   a efetivação da importação (DL-077) grava `importacao` com o lote como documento; o
   estorno herda a origem e o documento do original.
2. Origem e documento são imutáveis pelo ORM e por SQL direto (gatilho do PostgreSQL), com a
   única exceção do backfill da competência, que continua isolada.

Os testes do banco são PostgreSQL-only (o gatilho e as CHECKs de nome só existem lá; em
SQLite a regra fica no serviço). Dados sintéticos.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.db import DatabaseError, IntegrityError, connection, transaction

from apps.contabilidade.intercambio import importacao_lancamentos as servico
from apps.contabilidade.models import (
    Competencia,
    LancamentoContabil,
    LancamentoImutavelError,
    OrigemLancamento,
    TipoDocumentoOrigem,
    TipoPartida,
)
from apps.contabilidade.services import (
    ChaveIdempotenciaConflitante,
    LancamentoInvalido,
    criar_lancamento,
    estornar_lancamento,
    exige_permissao_de_estorno_automatico,
)
from apps.contabilidade.tests.cenario_dl077_exportacao import (
    CNPJ_DA_EMPRESA,
    criar_empresa,
    criar_escritorio,
    criar_plano,
)
from apps.contabilidade.tests.gatilhos_do_livro import gatilho_desligado
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

so_postgresql = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="O gatilho de origem e os nomes das CHECKs existem só em PostgreSQL (DL-089, 0026).",
)

# Gatilho de imutabilidade do lançamento (migração 0013, reescrita pelas 0017 e 0026).
IMUTAVEL_LANCAMENTO = ("contabilidade_lancamentocontabil", "trg_lancamento_contabil_imutavel")


@pytest.fixture
def cenario():
    escritorio = criar_escritorio("Escritório DL-089 origem", "89890000000189")
    empresa = criar_empresa(
        escritorio=escritorio, razao_social="Empresa DL-089 Origem Ltda", cnpj=CNPJ_DA_EMPRESA
    )
    contas = criar_plano(empresa)
    return {
        "escritorio": escritorio,
        "empresa": empresa,
        "caixa": contas["1.1.1"],
        "capital": contas["5.1"],
        "receita": contas["3.1"],
    }


def _itens(cenario, valor="100.00"):
    return [
        {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal(valor)},
        {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal(valor)},
    ]


def _lancar(cenario, **extra):
    return criar_lancamento(
        empresa=cenario["empresa"],
        data=date(2026, 3, 10),
        historico="Lançamento DL-089",
        itens=_itens(cenario),
        **extra,
    )


def _lote_de_importacao(cenario):
    """Um lote de importação recebido de verdade (DL-077, arquivo sintético). Não é
    efetivado: serve de documento de origem com identificador estável (o id do lote)."""
    conteudo = (
        "numero;data;historico;conta;lado;valor\r\n"
        "1;2026-03-10;Compra sintética;1.1.1;D;100.00\r\n"
        "1;2026-03-10;Compra sintética;5.1;C;100.00\r\n"
    ).encode("utf-8")
    return servico.receber(
        empresa=cenario["empresa"],
        formato="proprio",
        conteudo=conteudo,
        nome_arquivo="sintetico-dl089.txt",
        usuario=None,
    )


def _nome_da_restricao(erro):
    return erro.value.__cause__.diag.constraint_name


def _linhas(cenario):
    return LancamentoContabil.objects.filter(empresa=cenario["empresa"]).count()


# ---------------------------------------------------------------------------
# Critério 1 — caminhos atuais gravam a origem certa
# ---------------------------------------------------------------------------


def test_criar_lancamento_sem_origem_grava_manual_e_sem_documento(cenario):
    lancamento = _lancar(cenario)

    lancamento.refresh_from_db()
    assert lancamento.origem == OrigemLancamento.MANUAL
    assert lancamento.documento_origem_tipo is None
    assert lancamento.documento_origem_id is None
    assert exige_permissao_de_estorno_automatico(lancamento) is False


def test_criar_lancamento_com_origem_automatica_grava_origem_e_documento(cenario):
    lote = _lote_de_importacao(cenario)

    lancamento = _lancar(
        cenario,
        origem=OrigemLancamento.IMPORTACAO,
        documento_origem=(TipoDocumentoOrigem.IMPORTACAO_LANCAMENTOS, lote.pk),
    )

    lancamento.refresh_from_db()
    assert lancamento.origem == OrigemLancamento.IMPORTACAO
    assert lancamento.documento_origem_tipo == TipoDocumentoOrigem.IMPORTACAO_LANCAMENTOS
    # O identificador é guardado como TEXTO, mesmo quando veio como inteiro.
    assert lancamento.documento_origem_id == str(lote.pk)
    assert exige_permissao_de_estorno_automatico(lancamento) is True


def test_identificador_inteiro_e_gravado_como_texto_e_bool_e_recusado(cenario):
    lancamento = _lancar(
        cenario,
        origem=OrigemLancamento.IMPORTACAO,
        documento_origem=(TipoDocumentoOrigem.IMPORTACAO_LANCAMENTOS, 7),
    )
    lancamento.refresh_from_db()
    assert lancamento.documento_origem_id == "7"

    antes = _linhas(cenario)
    with pytest.raises(LancamentoInvalido):
        _lancar(
            cenario,
            origem=OrigemLancamento.IMPORTACAO,
            documento_origem=(TipoDocumentoOrigem.IMPORTACAO_LANCAMENTOS, True),
        )
    assert _linhas(cenario) == antes


@pytest.mark.parametrize(
    "origem, documento, motivo",
    [
        ("fiscal_inventada", None, "origem fora da lista"),
        ("manual", (TipoDocumentoOrigem.IMPORTACAO_LANCAMENTOS, "1"), "manual com documento"),
        ("importacao", ("tipo_inventado", "1"), "tipo de documento fora da lista"),
        ("importacao", (TipoDocumentoOrigem.IMPORTACAO_LANCAMENTOS, "   "), "identificador vazio"),
        (
            "importacao",
            (TipoDocumentoOrigem.IMPORTACAO_LANCAMENTOS, "9" * 65),
            "identificador longo",
        ),
        ("importacao", (TipoDocumentoOrigem.IMPORTACAO_LANCAMENTOS, "1\x00"), "caractere nulo"),
        ("importacao", (TipoDocumentoOrigem.IMPORTACAO_LANCAMENTOS, None), "identificador nulo"),
        ("importacao", "lote-1", "documento que não é par (tipo, identificador)"),
    ],
)
def test_origem_ou_documento_invalidos_sao_recusados_antes_de_gravar(
    cenario, origem, documento, motivo
):
    antes = _linhas(cenario)

    with pytest.raises(LancamentoInvalido):
        _lancar(cenario, origem=origem, documento_origem=documento)

    assert _linhas(cenario) == antes, f"gravou mesmo com {motivo}"


def test_idempotencia_mesma_chave_com_origem_diferente_e_conflito(cenario):
    primeiro = _lancar(cenario, chave_idempotencia="chave-dl089-origem")
    assert primeiro.criado_agora is True

    # A mesma chave, o mesmo conteúdo e a MESMA origem: devolve o lançamento já gravado.
    repetido = _lancar(cenario, chave_idempotencia="chave-dl089-origem")
    assert repetido.pk == primeiro.pk
    assert repetido.criado_agora is False

    # A mesma chave e o mesmo conteúdo, mas outra origem: conflito, nunca "sucesso".
    lote = _lote_de_importacao(cenario)
    antes = _linhas(cenario)
    with pytest.raises(ChaveIdempotenciaConflitante):
        _lancar(
            cenario,
            chave_idempotencia="chave-dl089-origem",
            origem=OrigemLancamento.IMPORTACAO,
            documento_origem=(TipoDocumentoOrigem.IMPORTACAO_LANCAMENTOS, lote.pk),
        )
    assert _linhas(cenario) == antes


def test_estorno_de_manual_continua_manual_e_sem_documento(cenario):
    original = _lancar(cenario)

    estorno = estornar_lancamento(original)

    estorno.refresh_from_db()
    assert estorno.origem == OrigemLancamento.MANUAL
    assert estorno.documento_origem_tipo is None


def test_estorno_de_automatico_herda_origem_e_documento_e_fica_marcado(cenario):
    lote = _lote_de_importacao(cenario)
    original = _lancar(
        cenario,
        origem=OrigemLancamento.IMPORTACAO,
        documento_origem=(TipoDocumentoOrigem.IMPORTACAO_LANCAMENTOS, lote.pk),
    )

    estorno = estornar_lancamento(original, papel=Papel.GESTOR)

    estorno.refresh_from_db()
    assert estorno.estorno_de_id == original.pk
    assert estorno.origem == OrigemLancamento.IMPORTACAO
    assert estorno.documento_origem_tipo == TipoDocumentoOrigem.IMPORTACAO_LANCAMENTOS
    assert estorno.documento_origem_id == str(lote.pk)


# ---------------------------------------------------------------------------
# Critério 2 — defesas do banco: CHECKs (PostgreSQL)
# ---------------------------------------------------------------------------


@so_postgresql
def test_banco_recusa_origem_inventada_por_insert_direto(cenario):
    with pytest.raises(IntegrityError) as erro:
        with transaction.atomic():
            LancamentoContabil.objects.create(
                empresa=cenario["empresa"],
                data=date(2026, 3, 10),
                historico="Origem inventada",
                origem="inventada",
            )

    # Reconferência, R1: origem que não é `manual` e não tem documento também cai no
    # pareamento. As duas CHECKs recusam; qual o PostgreSQL nomeia primeiro não é contrato.
    assert _nome_da_restricao(erro) in {
        "ck_lancamentocontabil_origem_valida",
        "ck_lancamentocontabil_origem_pareada_ao_documento",
    }


@so_postgresql
def test_banco_recusa_documento_em_lancamento_manual(cenario):
    with pytest.raises(IntegrityError) as erro:
        with transaction.atomic():
            LancamentoContabil.objects.create(
                empresa=cenario["empresa"],
                data=date(2026, 3, 10),
                historico="Manual com documento",
                origem=OrigemLancamento.MANUAL,
                documento_origem_tipo=TipoDocumentoOrigem.IMPORTACAO_LANCAMENTOS,
                documento_origem_id="1",
            )

    assert _nome_da_restricao(erro) == "ck_lancamentocontabil_documento_consistente"


@so_postgresql
def test_banco_recusa_documento_sem_identificador(cenario):
    with pytest.raises(IntegrityError) as erro:
        with transaction.atomic():
            LancamentoContabil.objects.create(
                empresa=cenario["empresa"],
                data=date(2026, 3, 10),
                historico="Documento pela metade",
                origem=OrigemLancamento.IMPORTACAO,
                documento_origem_tipo=TipoDocumentoOrigem.IMPORTACAO_LANCAMENTOS,
                documento_origem_id=None,
            )

    assert _nome_da_restricao(erro) == "ck_lancamentocontabil_documento_consistente"


@so_postgresql
def test_banco_recusa_tipo_de_documento_inventado(cenario):
    with pytest.raises(IntegrityError) as erro:
        with transaction.atomic():
            LancamentoContabil.objects.create(
                empresa=cenario["empresa"],
                data=date(2026, 3, 10),
                historico="Tipo inventado",
                origem=OrigemLancamento.IMPORTACAO,
                documento_origem_tipo="tipo_inventado",
                documento_origem_id="1",
            )

    assert _nome_da_restricao(erro) == "ck_lancamentocontabil_documento_tipo_valido"


# ---------------------------------------------------------------------------
# Critério 2 — imutabilidade: ORM e SQL direto (PostgreSQL)
# ---------------------------------------------------------------------------


def test_save_do_orm_nao_altera_origem_de_lancamento_efetivado(cenario):
    lote = _lote_de_importacao(cenario)
    lancamento = _lancar(
        cenario,
        origem=OrigemLancamento.IMPORTACAO,
        documento_origem=(TipoDocumentoOrigem.IMPORTACAO_LANCAMENTOS, lote.pk),
    )

    lancamento.origem = OrigemLancamento.MANUAL
    with pytest.raises(LancamentoImutavelError):
        lancamento.save()

    lancamento.refresh_from_db()
    assert lancamento.origem == OrigemLancamento.IMPORTACAO


@so_postgresql
def test_queryset_update_da_origem_e_recusado_e_nada_muda(cenario):
    lote = _lote_de_importacao(cenario)
    lancamento = _lancar(
        cenario,
        origem=OrigemLancamento.IMPORTACAO,
        documento_origem=(TipoDocumentoOrigem.IMPORTACAO_LANCAMENTOS, lote.pk),
    )

    with pytest.raises(DatabaseError) as erro:
        with transaction.atomic():
            LancamentoContabil.objects.filter(pk=lancamento.pk).update(
                origem=OrigemLancamento.MANUAL
            )

    assert _nome_da_restricao(erro) == "lancamento_origem_imutavel"
    lancamento.refresh_from_db()
    assert lancamento.origem == OrigemLancamento.IMPORTACAO


@so_postgresql
def test_queryset_update_do_documento_e_recusado_e_nada_muda(cenario):
    lote = _lote_de_importacao(cenario)
    lancamento = _lancar(
        cenario,
        origem=OrigemLancamento.IMPORTACAO,
        documento_origem=(TipoDocumentoOrigem.IMPORTACAO_LANCAMENTOS, lote.pk),
    )

    for campo, valor in (("documento_origem_id", "999999"), ("documento_origem_tipo", None)):
        with pytest.raises(DatabaseError) as erro:
            with transaction.atomic():
                LancamentoContabil.objects.filter(pk=lancamento.pk).update(**{campo: valor})
        assert _nome_da_restricao(erro) == "lancamento_origem_imutavel", campo

    lancamento.refresh_from_db()
    assert lancamento.documento_origem_tipo == TipoDocumentoOrigem.IMPORTACAO_LANCAMENTOS
    assert lancamento.documento_origem_id == str(lote.pk)


@so_postgresql
def test_sql_direto_nao_altera_origem_nem_documento(cenario):
    lote = _lote_de_importacao(cenario)
    lancamento = _lancar(
        cenario,
        origem=OrigemLancamento.IMPORTACAO,
        documento_origem=(TipoDocumentoOrigem.IMPORTACAO_LANCAMENTOS, lote.pk),
    )

    comandos = (
        "UPDATE contabilidade_lancamentocontabil SET origem = 'manual' WHERE id = %s",
        "UPDATE contabilidade_lancamentocontabil SET documento_origem_id = '1' WHERE id = %s",
        "UPDATE contabilidade_lancamentocontabil "
        "SET documento_origem_tipo = NULL, documento_origem_id = NULL WHERE id = %s",
    )
    for sql in comandos:
        with pytest.raises(DatabaseError) as erro:
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(sql, [lancamento.pk])
        assert _nome_da_restricao(erro) == "lancamento_origem_imutavel", sql

    lancamento.refresh_from_db()
    assert lancamento.origem == OrigemLancamento.IMPORTACAO
    assert lancamento.documento_origem_id == str(lote.pk)


@so_postgresql
def test_backfill_de_competencia_continua_permitido_em_lancamento_automatico(cenario):
    """A exceção do backfill (DL-016 F5) não foi alargada: preencher `competencia_id` de um
    lançamento de origem automática continua permitido, e a origem não muda com ele."""
    lote = _lote_de_importacao(cenario)
    lancamento = _lancar(
        cenario,
        origem=OrigemLancamento.IMPORTACAO,
        documento_origem=(TipoDocumentoOrigem.IMPORTACAO_LANCAMENTOS, lote.pk),
    )
    competencia = Competencia.objects.get(empresa=cenario["empresa"], ano=2026, mes=3)
    # Simula o lançamento anterior à DL-016 F2: sem competência gravada.
    with gatilho_desligado(IMUTAVEL_LANCAMENTO):
        LancamentoContabil.objects.filter(pk=lancamento.pk).update(competencia=None)

    LancamentoContabil.objects.filter(pk=lancamento.pk).update(competencia=competencia)

    lancamento.refresh_from_db()
    assert lancamento.competencia_id == competencia.pk
    assert lancamento.origem == OrigemLancamento.IMPORTACAO
    assert lancamento.documento_origem_id == str(lote.pk)
