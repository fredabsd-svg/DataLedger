"""DL-041 (RC-115/DE-077) — migração 0012: critérios 2 e 5 do plano.

- Backfill: `Estabelecimento` criado ANTES da 0012 ganha `escritorio_id`
  correto ao migrar para a frente (dado existente, não só banco vazio).
- Reversível ATÉ o limite declarado: reverter funciona sem dado
  conflitante; falha (declarado, não silenciado) se já houver a MESMA
  inscrição em dois escritórios — exatamente o estado que esta etapa
  passou a permitir.
"""

from __future__ import annotations

import pytest
from django.db import IntegrityError
from django.db import connection as db_connection
from django.db.migrations.executor import MigrationExecutor

from apps.empresas.models import Empresa, Estabelecimento, TipoEstabelecimento
from apps.tenancy.models import Escritorio

pytestmark = pytest.mark.django_db


_ALVO_ANTERIOR = [("empresas", "0011_bl533_bl534_gatilho_com_nome_e_trava")]


def _alvo_atual():
    return MigrationExecutor(db_connection).loader.graph.leaf_nodes("empresas")


def test_migracao_0012_preenche_escritorio_de_estabelecimento_existente():
    escritorio = Escritorio.objects.create(nome="Escritório Migração DL-041", cnpj="91100000000110")

    try:
        MigrationExecutor(db_connection).migrate(_ALVO_ANTERIOR)

        apps_antigos = MigrationExecutor(db_connection).loader.project_state(_ALVO_ANTERIOR).apps
        EmpresaAntes = apps_antigos.get_model("empresas", "Empresa")
        EstabelecimentoAntes = apps_antigos.get_model("empresas", "Estabelecimento")

        empresa_antes = EmpresaAntes.objects.create(
            escritorio_id=escritorio.id,
            razao_social="Empresa Pré-0012 Ltda",
            cnpj="11122233000183",
        )
        estabelecimento_antes = EstabelecimentoAntes.objects.create(
            empresa_id=empresa_antes.pk,
            tipo=TipoEstabelecimento.MATRIZ,
            nome="Matriz Pré-0012",
            cnpj="AB123CDE000155",
        )
        estabelecimento_id = estabelecimento_antes.pk

        with db_connection.cursor() as cursor:
            # Mesmo achado do teste equivalente da DL-039 (test_dl039_bl529_
            # gatilho_estabelecimento_cpf.py): FKs DEFERRABLE INITIALLY
            # DEFERRED deixam um gatilho pendente na tabela até o fim da
            # transação; migrações à frente que alterem essa tabela (aqui,
            # a 0012 adiciona uma coluna e uma constraint) precisam da
            # checagem IMEDIATA, não no commit.
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
    finally:
        MigrationExecutor(db_connection).migrate(_alvo_atual())

    estabelecimento = Estabelecimento.objects.get(pk=estabelecimento_id)
    assert estabelecimento.escritorio_id == escritorio.id


def test_migracao_0012_reverte_sem_dado_conflitante():
    # Reversão limpa: nenhuma inscrição repetida entre escritórios ainda.
    try:
        MigrationExecutor(db_connection).migrate(_ALVO_ANTERIOR)
    finally:
        MigrationExecutor(db_connection).migrate(_alvo_atual())


def test_migracao_0012_reverter_falha_com_cnpj_repetido_entre_escritorios():
    # Critério 5 do plano: o LIMITE declarado da reversibilidade. Depois
    # desta etapa, duas empresas podem, LEGITIMAMENTE, ter o mesmo CNPJ em
    # escritórios diferentes — reverter para a unicidade GLOBAL depois
    # disso tem que FALHAR (nunca silenciar apagando ou escolhendo uma das
    # duas), porque não há como restaurar "unicidade global" com um dado
    # que já a viola.
    escritorio_x = Escritorio.objects.create(nome="Escritório Reversão X", cnpj="91100000000111")
    escritorio_y = Escritorio.objects.create(nome="Escritório Reversão Y", cnpj="91100000000112")
    cnpj_repetido = "11122233000183"
    Empresa.objects.create(
        escritorio=escritorio_x, razao_social="Empresa X Reversão Ltda", cnpj=cnpj_repetido
    )
    Empresa.objects.create(
        escritorio=escritorio_y, razao_social="Empresa Y Reversão Ltda", cnpj=cnpj_repetido
    )
    # Mesmo achado de `test_migracao_0012_preenche_escritorio_de_
    # estabelecimento_existente` (FKs DEFERRABLE INITIALLY DEFERRED
    # deixam gatilho pendente na tabela até o commit) — sem isso, a
    # migração falharia por um `OperationalError` de "pending trigger
    # events", não pela `IntegrityError` de duplicidade que este teste
    # quer provar.
    with db_connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")

    with pytest.raises(IntegrityError):
        MigrationExecutor(db_connection).migrate(_ALVO_ANTERIOR)

    # A migração fica MEIO revertida dentro da transação que falhou —
    # Django já desfaz isso por conta própria (a operação inteira roda
    # dentro de uma transação de esquema); só confirmamos que dá para
    # seguir usando o banco normalmente depois, na versão ATUAL.
    MigrationExecutor(db_connection).migrate(_alvo_atual())
    assert Empresa.objects.filter(cnpj=cnpj_repetido).count() == 2
