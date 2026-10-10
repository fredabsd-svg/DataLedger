"""DL-089, correção da rodada 1 (T4 e A1): a migração 0026 com dado ANTERIOR a ela.

O `test_dl089_migracao.py` só cria dado depois de a 0026 estar aplicada. Aqui o lançamento é
gravado no estado 0025, com o modelo histórico daquele estado (`modelos_do_esquema`), e só
depois a migração roda. Isto prova o que a migração promete: o lançamento vira `manual` na
coluna, sem UPDATE e sem perder nada, e a checagem de estorno ainda o reconhece como automático
pela chave `importacao:` (A1).

PostgreSQL-only. `transaction=True` porque muda o schema, e cada teste volta ao estado mais novo.
Dados sintéticos.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor

from apps.contabilidade.models import LancamentoContabil, OrigemLancamento
from apps.contabilidade.services import (
    EstornoDeOrigemAutomaticaNaoPermitido,
    estornar_lancamento,
    exige_permissao_de_estorno_automatico,
)
from apps.contabilidade.tests.cenario_dl077_exportacao import (
    CNPJ_DA_EMPRESA,
    criar_empresa,
    criar_escritorio,
    criar_plano,
)
from apps.contabilidade.tests.gatilhos_do_livro import modelos_do_esquema
from apps.tenancy.models import Papel

ANTERIOR = [("contabilidade", "0025_dl077_correcao_auditoria_rodada_1")]
ATUAL = [("contabilidade", "0026_dl089_origem_do_lancamento")]
SHA_SINTETICO = "b" * 64

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(
        connection.vendor != "postgresql",
        reason="A função e o gatilho de origem existem só em PostgreSQL (DL-089, 0026).",
    ),
]


def _migrar(alvo):
    MigrationExecutor(connection).migrate(alvo)


@pytest.fixture
def cenario():
    escritorio = criar_escritorio("Escritório DL-089 migração anterior", "89895000000189")
    empresa = criar_empresa(
        escritorio=escritorio,
        razao_social="Empresa DL-089 Migração Anterior Ltda",
        cnpj=CNPJ_DA_EMPRESA,
    )
    return {"empresa": empresa, "contas": criar_plano(empresa)}


def _gravar_no_estado_anterior(cenario, *, chave, historico):
    """Grava, no estado 0025, um lançamento equilibrado com a chave dada e devolve o id.

    Usa os modelos HISTÓRICOS do estado 0025: o modelo atual tem as colunas `origem` e
    documento, que aquele estado não tem.
    """
    historicos = modelos_do_esquema(ANTERIOR)
    Lancamento = historicos.get_model("contabilidade", "LancamentoContabil")
    Item = historicos.get_model("contabilidade", "ItemLancamento")
    contas = cenario["contas"]
    with transaction.atomic():
        lancamento = Lancamento.objects.create(
            empresa_id=cenario["empresa"].pk,
            data=date(2026, 3, 10),
            historico=historico,
            chave_idempotencia=chave,
        )
        Item.objects.create(
            lancamento_id=lancamento.pk,
            conta_id=contas["1.1.1"].pk,
            tipo="debito",
            valor=Decimal("25.00"),
        )
        Item.objects.create(
            lancamento_id=lancamento.pk,
            conta_id=contas["5.1"].pk,
            tipo="credito",
            valor=Decimal("25.00"),
        )
    return lancamento.pk


def test_t4_importacao_gravada_antes_da_0026_vira_manual_sem_perder_a_chave(cenario):
    try:
        _migrar(ANTERIOR)
        lancamento_id = _gravar_no_estado_anterior(
            cenario, chave=f"importacao:{SHA_SINTETICO}:1", historico="Importado antes da 0026"
        )
        _migrar(ATUAL)
    finally:
        _migrar(ATUAL)

    lancamento = LancamentoContabil.objects.get(pk=lancamento_id)
    assert lancamento.origem == OrigemLancamento.MANUAL
    assert lancamento.documento_origem_tipo is None
    assert lancamento.documento_origem_id is None
    assert lancamento.chave_idempotencia == f"importacao:{SHA_SINTETICO}:1"


def test_a1_importacao_anterior_a_0026_continua_exigindo_permissao_de_estorno(cenario):
    """A1 de ponta a ponta: o dado antigo, depois da migração, é recusado para quem não estorna
    automático, e aceito para ADMINISTRADOR e GESTOR."""
    try:
        _migrar(ANTERIOR)
        lancamento_id = _gravar_no_estado_anterior(
            cenario, chave=f"importacao:{SHA_SINTETICO}:2", historico="Importado antes da 0026"
        )
        _migrar(ATUAL)
    finally:
        _migrar(ATUAL)

    lancamento = LancamentoContabil.objects.get(pk=lancamento_id)
    assert exige_permissao_de_estorno_automatico(lancamento) is True
    for papel in (Papel.ANALISTA, Papel.FINANCEIRO):
        with pytest.raises(EstornoDeOrigemAutomaticaNaoPermitido):
            estornar_lancamento(lancamento, papel=papel)
    assert LancamentoContabil.objects.filter(estorno_de=lancamento).count() == 0

    estorno = estornar_lancamento(lancamento, papel=Papel.GESTOR)
    assert estorno.estorno_de_id == lancamento.pk


def test_t4_lancamento_manual_sem_chave_anterior_a_0026_segue_estornavel_por_quem_lanca(cenario):
    """Sem regressão: o digitado antes da 0026 continua livre para ANALISTA."""
    try:
        _migrar(ANTERIOR)
        lancamento_id = _gravar_no_estado_anterior(cenario, chave=None, historico="Digitado antes")
        _migrar(ATUAL)
    finally:
        _migrar(ATUAL)

    lancamento = LancamentoContabil.objects.get(pk=lancamento_id)
    assert exige_permissao_de_estorno_automatico(lancamento) is False
    estorno = estornar_lancamento(lancamento, papel=Papel.ANALISTA)
    assert estorno.origem == OrigemLancamento.MANUAL
