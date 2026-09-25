"""Achado B8 da auditoria rodada 1 (DL-038): `modo_escrituracao` não tinha
restrição de domínio no banco — `Empresa.objects.create(...,
modo_escrituracao="qualquer")` gravava, e `apps.empresas.services.
recusar_se_livro_caixa` passava a tratar essa empresa como "contabilidade"
(só recusa o valor exato "livro_caixa"). Migração 0009 fecha isso com uma
`CheckConstraint` de domínio.
"""

from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction

from apps.empresas.models import Empresa, ModoEscrituracao
from apps.tenancy.models import Escritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def escritorio():
    return Escritorio.objects.create(nome="Escritório B8", cnpj="91100000000060")


def test_modo_escrituracao_fora_do_dominio_e_recusado_pelo_banco(escritorio):
    with pytest.raises(IntegrityError, match="empresa_modo_escrituracao_valido"):
        with transaction.atomic():
            Empresa.objects.create(
                escritorio=escritorio,
                razao_social="Empresa Modo Inválido B8 Ltda",
                cnpj="11122233000183",
                modo_escrituracao="qualquer",
            )


def test_bulk_create_com_modo_invalido_tambem_e_recusado(escritorio):
    # A CheckConstraint é a camada que sobrevive a bulk_create (camada 1 da
    # DE-008) — diferente de validação de campo/serializer, que bulk_create
    # nunca aciona.
    with pytest.raises(IntegrityError, match="empresa_modo_escrituracao_valido"):
        with transaction.atomic():
            Empresa.objects.bulk_create(
                [
                    Empresa(
                        escritorio=escritorio,
                        razao_social="Empresa Bulk Modo Inválido B8 Ltda",
                        cnpj="11122233000183",
                        modo_escrituracao="invalido",
                    )
                ]
            )


@pytest.mark.parametrize("modo", [ModoEscrituracao.CONTABILIDADE, ModoEscrituracao.LIVRO_CAIXA])
def test_modo_escrituracao_valido_e_aceito(escritorio, modo):
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social=f"Empresa Modo {modo} B8 Ltda",
        cnpj="11122233000183",
        modo_escrituracao=modo,
    )
    empresa.refresh_from_db()
    assert empresa.modo_escrituracao == modo


@pytest.mark.django_db(transaction=True)
def test_migracao_0009_aplica_em_banco_com_empresas_existentes_sem_alterar_dado():
    from django.db import connection as db_connection
    from django.db.migrations.executor import MigrationExecutor

    escritorio = Escritorio.objects.create(nome="Escritório Migração B8", cnpj="91100000000061")

    alvo_anterior = [("empresas", "0008_dl038_cliente_pessoa_fisica")]
    alvo_atual = MigrationExecutor(db_connection).loader.graph.leaf_nodes("empresas")
    try:
        MigrationExecutor(db_connection).migrate(alvo_anterior)

        apps_antigos = MigrationExecutor(db_connection).loader.project_state(alvo_anterior).apps
        EmpresaAntes = apps_antigos.get_model("empresas", "Empresa")
        empresa_antes = EmpresaAntes.objects.create(
            escritorio_id=escritorio.id,
            razao_social="Empresa Pré-Existente B8 Ltda",
            cnpj="11122233000183",
            modo_escrituracao="contabilidade",
        )
        empresa_id = empresa_antes.pk
    finally:
        MigrationExecutor(db_connection).migrate(alvo_atual)

    empresa = Empresa.objects.get(pk=empresa_id)
    assert empresa.modo_escrituracao == ModoEscrituracao.CONTABILIDADE

    # A migração é reversível — sem empresa com modo inválido na base
    # (nenhuma teria conseguido entrar antes da 0009, já que o valor
    # sempre veio do `default=`/enum), a reversão sempre funciona.
    try:
        MigrationExecutor(db_connection).migrate(alvo_anterior)
    finally:
        MigrationExecutor(db_connection).migrate(alvo_atual)
