"""DL-038, critério 1 do plano — migração `0008_dl038_cliente_pessoa_fisica`
em banco vazio E sobre base com empresas existentes: todas ficam CNPJ e
contabilidade, nenhum dado muda, e a migração reverte.

Mesmo padrão de `apps/contabilidade/tests/test_dl033_migracao.py`: volta o
schema de `empresas` para ANTES desta migração (0007), grava com o modelo
HISTÓRICO (sem os campos novos), reaplica a migração e confere com o modelo
ATUAL — e, ao final, confere que `migrate empresas 0007` reverte sem erro
(cenário sem empresa CPF cadastrada, exatamente o caso que o plano declara
seguro em "Riscos e reversão").
"""

import pytest

from apps.empresas.models import Empresa, TipoInscricao
from apps.tenancy.models import Escritorio

pytestmark = pytest.mark.django_db


@pytest.mark.django_db(transaction=True)
def test_migracao_0008_sobre_base_com_empresas_existentes_nao_altera_dado():
    from django.db import connection as db_connection
    from django.db.migrations.executor import MigrationExecutor

    escritorio = Escritorio.objects.create(nome="Escritório Migração DL-038", cnpj="50505050000150")

    alvo_anterior = [("empresas", "0007_bl54_cnpj_check_constraint_formato")]
    alvo_atual = MigrationExecutor(db_connection).loader.graph.leaf_nodes("empresas")
    try:
        # Volta o SCHEMA de `empresas` para ANTES desta migração — as
        # colunas `cpf`, `tipo_inscricao` e `modo_escrituracao` não
        # existem na tabela ainda.
        MigrationExecutor(db_connection).migrate(alvo_anterior)

        # Modelo HISTÓRICO, congelado em 0007 — nunca o `Empresa` importado
        # no topo deste arquivo, que já tem os campos novos e quebraria o
        # INSERT contra o schema antigo.
        apps_antigos = MigrationExecutor(db_connection).loader.project_state(alvo_anterior).apps
        EmpresaAntes = apps_antigos.get_model("empresas", "Empresa")
        empresa_antes = EmpresaAntes.objects.create(
            escritorio_id=escritorio.id,
            razao_social="Empresa Pré-Existente Ltda",
            cnpj="11122233000183",
        )
        empresa_id = empresa_antes.pk
    finally:
        # SEMPRE volta ao estado mais recente antes de sair — inclusive se
        # uma asserção falhar abaixo.
        MigrationExecutor(db_connection).migrate(alvo_atual)

    empresa = Empresa.objects.get(pk=empresa_id)
    # Critério 1: toda empresa existente vira CNPJ + contabilidade, sem
    # alterar o CNPJ que já tinha.
    assert empresa.tipo_inscricao == TipoInscricao.CNPJ
    assert empresa.modo_escrituracao == "contabilidade"
    assert empresa.cnpj == "11122233000183"
    assert empresa.cpf == ""
    assert empresa.razao_social == "Empresa Pré-Existente Ltda"


@pytest.mark.django_db(transaction=True)
def test_migracao_0008_em_banco_vazio_nao_levanta_erro():
    from django.db import connection as db_connection
    from django.db.migrations.executor import MigrationExecutor

    alvo_anterior = [("empresas", "0007_bl54_cnpj_check_constraint_formato")]
    alvo_atual = MigrationExecutor(db_connection).loader.graph.leaf_nodes("empresas")
    try:
        MigrationExecutor(db_connection).migrate(alvo_anterior)
        # Nenhum dado gravado — banco vazio na hora de migrar para frente.
    finally:
        MigrationExecutor(db_connection).migrate(alvo_atual)

    # A tabela chegou ao estado atual sem erro; uma criação normal pelo
    # modelo ATUAL confirma que o schema resultante está utilizável.
    escritorio = Escritorio.objects.create(nome="Escritório Vazio DL-038", cnpj="60606060000160")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Nova Ltda", cnpj="11122233000183"
    )
    assert empresa.tipo_inscricao == TipoInscricao.CNPJ
    assert empresa.modo_escrituracao == "contabilidade"


@pytest.mark.django_db(transaction=True)
def test_migracao_0008_reverte_sem_empresa_cpf_cadastrada():
    from django.db import connection as db_connection
    from django.db.migrations.executor import MigrationExecutor

    # Cenário que o plano declara SEGURO em "Riscos e reversão": reverter
    # só é seguro sem empresa CPF cadastrada. Este teste fixa exatamente
    # esse caso — com uma empresa CNPJ comum na base, a reversão para 0007
    # tem que funcionar sem erro (a coluna `cpf` dela é sempre "" e a
    # AlterField do `cnpj` é reversível).
    escritorio = Escritorio.objects.create(nome="Escritório Reversão DL-038", cnpj="70707070000170")
    Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Antes da Reversão Ltda", cnpj="11122233000183"
    )

    alvo_anterior = [("empresas", "0007_bl54_cnpj_check_constraint_formato")]
    alvo_atual = MigrationExecutor(db_connection).loader.graph.leaf_nodes("empresas")
    try:
        # A própria chamada de `migrate` para trás é a asserção: se a
        # migração não fosse reversível (RunPython irreversível, por
        # exemplo), isto levantaria `IrreversibleError` aqui.
        MigrationExecutor(db_connection).migrate(alvo_anterior)
    finally:
        # Sempre volta ao estado atual, mesmo se a reversão acima falhar —
        # não deixa o schema capenga para o restante da suíte.
        MigrationExecutor(db_connection).migrate(alvo_atual)
