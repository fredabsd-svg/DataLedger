"""Achado B2 (ressalva) e N18 da reconferência DL-010/DL-038 — BL-529
(DL-039): "estabelecimento é conceito de pessoa jurídica" só tinha defesa
em Python (`Estabelecimento.clean()`, `EstabelecimentoListCreateView.
perform_create`) — nenhuma no BANCO. A reconferência mediu: um
`Estabelecimento` criado por ORM DIRETO (`objects.create()`, que nunca
chama `full_clean()`) para uma empresa CPF era aceito, e a recepção fiscal
chegava a VINCULAR a nota a essa pessoa física por ele (`recebido`,
`('CPF', 'prestador')`).

A migração 0010 (apps/empresas/migrations/
0010_bl529_gatilho_estabelecimento_empresa_cpf.py) fecha os dois lados da
invariante com gatilhos do PostgreSQL — a única ferramenta que expressa
checagem ENTRE tabelas (uma `CheckConstraint` não alcança); a decisão e o
motivo estão documentados na própria migração.

Estes testes usam `objects.create()`/`objects.filter().update()` DIRETO —
nunca `full_clean()` — de propósito: é exatamente o caminho que a camada
Python (achado B2/N18, já coberto em test_dl076_b2_estabelecimento_cpf.py)
NÃO alcança.
"""

from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction

from apps.empresas.models import Empresa, Estabelecimento, TipoEstabelecimento, TipoInscricao
from apps.tenancy.models import Escritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def escritorio():
    return Escritorio.objects.create(nome="Escritório BL-529", cnpj="91100000000070")


@pytest.fixture
def empresa_cpf(escritorio):
    return Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Fulano BL-529",
        tipo_inscricao=TipoInscricao.CPF,
        cpf="11144477735",
        cnpj="",
    )


@pytest.fixture
def empresa_cnpj(escritorio):
    return Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa CNPJ BL-529 Ltda", cnpj="11122233000183"
    )


def test_objects_create_de_estabelecimento_para_empresa_cpf_e_recusado_pelo_banco(empresa_cpf):
    # `objects.create()` NUNCA chama `full_clean()` — sem o gatilho, isso
    # gravava. O gatilho `trg_estabelecimento_recusa_empresa_cpf` é a
    # ÚNICA defesa que este caminho atravessa.
    with pytest.raises(IntegrityError, match="pessoa jurídica"):
        with transaction.atomic():
            Estabelecimento.objects.create(
                empresa=empresa_cpf,
                tipo=TipoEstabelecimento.MATRIZ,
                nome="Matriz Indevida BL-529",
                cnpj="11122233000183",
            )
    assert not Estabelecimento.objects.filter(empresa=empresa_cpf).exists()


def test_bulk_create_de_estabelecimento_para_empresa_cpf_tambem_e_recusado(empresa_cpf):
    # `bulk_create()` é OUTRO caminho que `full_clean()` nunca alcança
    # (camada 1 da DE-008 — só o gatilho sobrevive a este caminho).
    with pytest.raises(IntegrityError, match="pessoa jurídica"):
        with transaction.atomic():
            Estabelecimento.objects.bulk_create(
                [
                    Estabelecimento(
                        empresa=empresa_cpf,
                        tipo=TipoEstabelecimento.MATRIZ,
                        nome="Matriz Bulk BL-529",
                        cnpj="11122233000183",
                    )
                ]
            )
    assert not Estabelecimento.objects.filter(empresa=empresa_cpf).exists()


def test_objects_create_de_estabelecimento_para_empresa_cnpj_continua_permitido(empresa_cnpj):
    # Controle: o gatilho não pode recusar o caso NORMAL (empresa CNPJ).
    estabelecimento = Estabelecimento.objects.create(
        empresa=empresa_cnpj,
        tipo=TipoEstabelecimento.MATRIZ,
        nome="Matriz Válida BL-529",
        cnpj="11122233000183",
    )
    assert estabelecimento.pk is not None


def test_queryset_update_de_empresa_para_cpf_com_estabelecimento_e_recusado_pelo_banco(
    empresa_cnpj,
):
    # `QuerySet.update()` NUNCA chama `save()` nem `full_clean()` — sem o
    # gatilho, `Empresa.clean()` (achado N18) nunca chega a rodar por este
    # caminho. O gatilho `trg_empresa_recusa_transicao_cpf_com_
    # estabelecimento` é a defesa que sobra.
    Estabelecimento.objects.create(
        empresa=empresa_cnpj,
        tipo=TipoEstabelecimento.MATRIZ,
        nome="Matriz BL-529",
        cnpj="11122233000183",
    )
    with pytest.raises(IntegrityError, match="estabelecimento"):
        with transaction.atomic():
            Empresa.objects.filter(pk=empresa_cnpj.pk).update(
                tipo_inscricao=TipoInscricao.CPF, cnpj="", cpf="11144477735"
            )
    empresa_cnpj.refresh_from_db()
    assert empresa_cnpj.tipo_inscricao == TipoInscricao.CNPJ


def test_queryset_update_de_empresa_para_cpf_sem_estabelecimento_e_permitido(escritorio):
    # Controle negativo: a MESMA operação, sem estabelecimento gravado,
    # continua permitida pelo gatilho.
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Sem Filial BL-529 Ltda", cnpj="11122233000183"
    )
    Empresa.objects.filter(pk=empresa.pk).update(
        tipo_inscricao=TipoInscricao.CPF, cnpj="", cpf="22255588846"
    )
    empresa.refresh_from_db()
    assert empresa.tipo_inscricao == TipoInscricao.CPF


def test_migracao_0010_aplica_e_reverte_sem_alterar_dado_existente(escritorio):
    from django.db import connection as db_connection
    from django.db.migrations.executor import MigrationExecutor

    alvo_anterior = [("empresas", "0009_empresa_empresa_modo_escrituracao_valido")]
    alvo_atual = MigrationExecutor(db_connection).loader.graph.leaf_nodes("empresas")
    try:
        MigrationExecutor(db_connection).migrate(alvo_anterior)

        apps_antigos = MigrationExecutor(db_connection).loader.project_state(alvo_anterior).apps
        EmpresaAntes = apps_antigos.get_model("empresas", "Empresa")
        empresa_antes = EmpresaAntes.objects.create(
            escritorio_id=escritorio.id,
            razao_social="Empresa Pré-Existente BL-529 Ltda",
            cnpj="11122233000183",
        )
        empresa_id = empresa_antes.pk
        # Achado da DL-041: as FKs do Django são DEFERRABLE INITIALLY
        # DEFERRED — o INSERT acima deixa um gatilho de checagem de FK
        # PENDENTE em `empresas_empresa` até o fim da transação (o
        # `pytest.mark.django_db` desta suíte). Migrações posteriores à
        # 0010 (a partir da 0012, DL-041) acrescentam `AddConstraint` em
        # `empresas_empresa` — e o PostgreSQL recusa `CREATE UNIQUE INDEX`
        # numa tabela com gatilho pendente (`ObjectInUse: cannot CREATE
        # INDEX ... because it has pending trigger events`). Forçar a
        # checagem AGORA (em vez de esperar o fim da transação) resolve —
        # sem isso, o `MigrationExecutor(...).migrate(alvo_atual)` do
        # `finally` quebraria por um motivo que nada tem a ver com o que
        # este teste verifica.
        with db_connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
    finally:
        MigrationExecutor(db_connection).migrate(alvo_atual)

    empresa = Empresa.objects.get(pk=empresa_id)
    assert empresa.razao_social == "Empresa Pré-Existente BL-529 Ltda"

    # Reversível: `migrate empresas 0009` remove os gatilhos sem tocar em
    # dado nenhum (nenhuma coluna nova, nenhuma reescrita de linha).
    try:
        MigrationExecutor(db_connection).migrate(
            [("empresas", "0009_empresa_empresa_modo_escrituracao_valido")]
        )
    finally:
        MigrationExecutor(db_connection).migrate(alvo_atual)
