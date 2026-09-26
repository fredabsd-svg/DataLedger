"""DL-041 (RC-115/DE-077, decisão do Fred na PE-68): CNPJ e CPF passam a
ser únicos POR ESCRITÓRIO — não mais no sistema inteiro (BL-48, que
fechava a PE-21 e a PE-68/B6 da auditoria rodada 1 da DL-010/DL-038).

Cobre os critérios do plano (docs/planos/DL-041-unicidade-por-escritorio.md):
  1. Empresa: CNPJ/CPF únicos por (escritório, inscrição); o MESMO CNPJ/CPF
     pode existir em escritórios diferentes.
  2. Estabelecimento: CNPJ único dentro do escritório da empresa.
  3/4. Duplicata no MESMO escritório continua recusada (400/formulário,
     nunca 500), com mensagem que só fala do PRÓPRIO escritório; em OUTRO
     escritório é aceita, pela API e pelo admin.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import Client
from django.urls import reverse

from apps.empresas.models import Empresa, Estabelecimento, TipoEstabelecimento
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


def _gestor_de_escritorio(nome_escritorio, cnpj_escritorio, username):
    escritorio = Escritorio.objects.create(nome=nome_escritorio, cnpj=cnpj_escritorio)
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@x.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return escritorio, usuario


@pytest.fixture
def escritorio_a():
    escritorio, usuario = _gestor_de_escritorio(
        "Escritório A DL-041", "91100000000101", "gestor-a-dl041"
    )
    return escritorio, usuario


@pytest.fixture
def escritorio_b():
    escritorio, usuario = _gestor_de_escritorio(
        "Escritório B DL-041", "91100000000102", "gestor-b-dl041"
    )
    return escritorio, usuario


# --- Critério 1: Empresa, CNPJ/CPF por escritório -----------------------


def test_criar_empresa_com_mesmo_cnpj_em_dois_escritorios_e_aceito_nos_dois(
    escritorio_a, escritorio_b
):
    _, usuario_a = escritorio_a
    _, usuario_b = escritorio_b
    cnpj_compartilhado = "11122233000183"

    client_a = Client()
    client_a.login(username="gestor-a-dl041", password="senha-forte-123")
    resposta_a = client_a.post(
        reverse("empresas:api-lista"),
        data={"razao_social": "Empresa Compartilhada A Ltda", "cnpj": cnpj_compartilhado},
        content_type="application/json",
    )
    assert resposta_a.status_code == 201, resposta_a.content

    client_b = Client()
    client_b.login(username="gestor-b-dl041", password="senha-forte-123")
    resposta_b = client_b.post(
        reverse("empresas:api-lista"),
        data={"razao_social": "Empresa Compartilhada B Ltda", "cnpj": cnpj_compartilhado},
        content_type="application/json",
    )
    assert resposta_b.status_code == 201, resposta_b.content

    assert Empresa.objects.filter(cnpj=cnpj_compartilhado).count() == 2


def test_criar_empresa_com_mesmo_cnpj_no_mesmo_escritorio_continua_recusado_com_400(
    escritorio_a,
):
    _, usuario_a = escritorio_a
    cnpj = "11122233000183"
    client = Client()
    client.login(username="gestor-a-dl041", password="senha-forte-123")

    resposta_1 = client.post(
        reverse("empresas:api-lista"),
        data={"razao_social": "Empresa Original Ltda", "cnpj": cnpj},
        content_type="application/json",
    )
    assert resposta_1.status_code == 201

    resposta_2 = client.post(
        reverse("empresas:api-lista"),
        data={"razao_social": "Empresa Duplicada Ltda", "cnpj": cnpj},
        content_type="application/json",
    )
    assert resposta_2.status_code == 400, resposta_2.content
    (mensagem,) = resposta_2.json()["cnpj"]
    # Critério 4: a mensagem só fala do PRÓPRIO escritório — nunca sugere
    # unicidade global.
    assert "neste escritório" in mensagem
    assert Empresa.objects.filter(cnpj=cnpj).count() == 1


def test_criar_empresa_com_mesmo_cpf_em_dois_escritorios_e_aceito_nos_dois(
    escritorio_a, escritorio_b
):
    cpf_compartilhado = "11144477735"

    client_a = Client()
    client_a.login(username="gestor-a-dl041", password="senha-forte-123")
    resposta_a = client_a.post(
        reverse("empresas:api-lista"),
        data={
            "razao_social": "Fulano Compartilhado A",
            "tipo_inscricao": "CPF",
            "cpf": cpf_compartilhado,
        },
        content_type="application/json",
    )
    assert resposta_a.status_code == 201, resposta_a.content

    client_b = Client()
    client_b.login(username="gestor-b-dl041", password="senha-forte-123")
    resposta_b = client_b.post(
        reverse("empresas:api-lista"),
        data={
            "razao_social": "Fulano Compartilhado B",
            "tipo_inscricao": "CPF",
            "cpf": cpf_compartilhado,
        },
        content_type="application/json",
    )
    assert resposta_b.status_code == 201, resposta_b.content

    assert Empresa.objects.filter(cpf=cpf_compartilhado).count() == 2


def test_banco_recusa_direto_mesmo_cnpj_no_mesmo_escritorio_mas_aceita_em_outro(
    escritorio_a, escritorio_b
):
    # Camada 1 da DE-008: mesmo sem passar pela API, a UniqueConstraint do
    # banco garante a mesma política (por escritório).
    escritorio_a_obj, _ = escritorio_a
    escritorio_b_obj, _ = escritorio_b
    cnpj = "11122233000183"

    Empresa.objects.create(
        escritorio=escritorio_a_obj, razao_social="Empresa A Original Ltda", cnpj=cnpj
    )

    with pytest.raises(IntegrityError, match="empresa_cnpj_unico_por_escritorio"):
        with transaction.atomic():
            Empresa.objects.create(
                escritorio=escritorio_a_obj, razao_social="Empresa A Duplicada Ltda", cnpj=cnpj
            )

    # Em outro escritório, o MESMO cnpj é aceito sem restrição alguma.
    Empresa.objects.create(escritorio=escritorio_b_obj, razao_social="Empresa B Ltda", cnpj=cnpj)
    assert Empresa.objects.filter(cnpj=cnpj).count() == 2


# --- Admin: mesma política -----------------------------------------------


def _payload_admin_base(escritorio):
    return {
        "escritorio": escritorio.pk,
        "nome_fantasia": "",
        "tipo_inscricao": "CNPJ",
        "cnpj": "",
        "cpf": "",
        "modo_escrituracao": "contabilidade",
        "ativo": "on",
        "estabelecimentos-TOTAL_FORMS": "0",
        "estabelecimentos-INITIAL_FORMS": "0",
        "estabelecimentos-MIN_NUM_FORMS": "0",
        "estabelecimentos-MAX_NUM_FORMS": "1000",
    }


@pytest.fixture
def superusuario():
    return get_user_model().objects.create_superuser(
        username="admin-dl041", password="senha-forte-123", email="admin-dl041@x.com.br"
    )


def test_admin_cria_empresa_com_mesmo_cnpj_de_outro_escritorio_com_sucesso(
    escritorio_a, escritorio_b, superusuario
):
    escritorio_a_obj, _ = escritorio_a
    escritorio_b_obj, _ = escritorio_b
    cnpj = "11122233000183"
    Empresa.objects.create(
        escritorio=escritorio_a_obj, razao_social="Empresa A Admin Ltda", cnpj=cnpj
    )

    client = Client()
    client.login(username="admin-dl041", password="senha-forte-123")
    payload = _payload_admin_base(escritorio_b_obj)
    payload.update({"razao_social": "Empresa B Admin Ltda", "cnpj": cnpj})
    resposta = client.post(reverse("admin:empresas_empresa_add"), data=payload)

    assert resposta.status_code == 302, resposta.content
    assert Empresa.objects.filter(cnpj=cnpj).count() == 2


def test_admin_cria_empresa_com_mesmo_cnpj_do_mesmo_escritorio_da_200_com_erro(
    escritorio_a, superusuario
):
    escritorio_a_obj, _ = escritorio_a
    cnpj = "11122233000183"
    Empresa.objects.create(
        escritorio=escritorio_a_obj, razao_social="Empresa A Admin Original Ltda", cnpj=cnpj
    )

    client = Client()
    client.login(username="admin-dl041", password="senha-forte-123")
    payload = _payload_admin_base(escritorio_a_obj)
    payload.update({"razao_social": "Empresa A Admin Duplicada Ltda", "cnpj": cnpj})
    resposta = client.post(reverse("admin:empresas_empresa_add"), data=payload)

    assert resposta.status_code == 200, resposta.content
    conteudo = resposta.content.decode()
    assert "já existe neste escritório" in conteudo
    assert Empresa.objects.filter(cnpj=cnpj).count() == 1


# --- Critério 2: Estabelecimento, CNPJ por escritório --------------------


def test_criar_estabelecimento_com_mesmo_cnpj_em_dois_escritorios_e_aceito_nos_dois(
    escritorio_a, escritorio_b
):
    escritorio_a_obj, usuario_a = escritorio_a
    escritorio_b_obj, usuario_b = escritorio_b
    cnpj_filial = "AB123CDE000155"

    empresa_a = Empresa.objects.create(
        escritorio=escritorio_a_obj, razao_social="Empresa A Estab Ltda", cnpj="11122233000183"
    )
    empresa_b = Empresa.objects.create(
        escritorio=escritorio_b_obj, razao_social="Empresa B Estab Ltda", cnpj="44455566000183"
    )

    client_a = Client()
    client_a.login(username="gestor-a-dl041", password="senha-forte-123")
    resposta_a = client_a.post(
        reverse("empresas:api-estabelecimentos", kwargs={"empresa_id": empresa_a.pk}),
        data={"tipo": "matriz", "nome": "Matriz A", "cnpj": cnpj_filial},
        content_type="application/json",
    )
    assert resposta_a.status_code == 201, resposta_a.content

    client_b = Client()
    client_b.login(username="gestor-b-dl041", password="senha-forte-123")
    resposta_b = client_b.post(
        reverse("empresas:api-estabelecimentos", kwargs={"empresa_id": empresa_b.pk}),
        data={"tipo": "matriz", "nome": "Matriz B", "cnpj": cnpj_filial},
        content_type="application/json",
    )
    assert resposta_b.status_code == 201, resposta_b.content

    assert Estabelecimento.objects.filter(cnpj=cnpj_filial).count() == 2
    # A coluna desnormalizada reflete o escritório de cada empresa.
    est_a = Estabelecimento.objects.get(empresa=empresa_a)
    est_b = Estabelecimento.objects.get(empresa=empresa_b)
    assert est_a.escritorio_id == escritorio_a_obj.pk
    assert est_b.escritorio_id == escritorio_b_obj.pk


def test_criar_estabelecimento_com_mesmo_cnpj_no_mesmo_escritorio_e_recusado(escritorio_a):
    escritorio_a_obj, usuario_a = escritorio_a
    cnpj_filial = "AB123CDE000155"

    empresa_1 = Empresa.objects.create(
        escritorio=escritorio_a_obj, razao_social="Empresa 1 Ltda", cnpj="11122233000183"
    )
    empresa_2 = Empresa.objects.create(
        escritorio=escritorio_a_obj, razao_social="Empresa 2 Ltda", cnpj="44455566000183"
    )
    Estabelecimento.objects.create(
        empresa=empresa_1, tipo=TipoEstabelecimento.MATRIZ, nome="Matriz 1", cnpj=cnpj_filial
    )

    client = Client()
    client.login(username="gestor-a-dl041", password="senha-forte-123")
    resposta = client.post(
        reverse("empresas:api-estabelecimentos", kwargs={"empresa_id": empresa_2.pk}),
        data={"tipo": "matriz", "nome": "Matriz 2", "cnpj": cnpj_filial},
        content_type="application/json",
    )

    assert resposta.status_code == 400, resposta.content
    assert Estabelecimento.objects.filter(cnpj=cnpj_filial).count() == 1


def test_estabelecimento_por_orm_direto_grava_escritorio_derivado_da_empresa(escritorio_a):
    escritorio_a_obj, _ = escritorio_a
    empresa = Empresa.objects.create(
        escritorio=escritorio_a_obj, razao_social="Empresa ORM Ltda", cnpj="11122233000183"
    )
    estabelecimento = Estabelecimento.objects.create(
        empresa=empresa, tipo=TipoEstabelecimento.MATRIZ, nome="Matriz", cnpj="AB123CDE000155"
    )
    assert estabelecimento.escritorio_id == escritorio_a_obj.pk


def test_banco_recusa_mesmo_cnpj_de_estabelecimento_no_mesmo_escritorio_mas_aceita_em_outro(
    escritorio_a, escritorio_b
):
    escritorio_a_obj, _ = escritorio_a
    escritorio_b_obj, _ = escritorio_b
    cnpj_filial = "AB123CDE000155"

    empresa_a1 = Empresa.objects.create(
        escritorio=escritorio_a_obj, razao_social="Empresa A1 Ltda", cnpj="11122233000183"
    )
    empresa_a2 = Empresa.objects.create(
        escritorio=escritorio_a_obj, razao_social="Empresa A2 Ltda", cnpj="44455566000183"
    )
    empresa_b = Empresa.objects.create(
        escritorio=escritorio_b_obj, razao_social="Empresa B Ltda", cnpj="77788899000183"
    )
    Estabelecimento.objects.create(
        empresa=empresa_a1, tipo=TipoEstabelecimento.MATRIZ, nome="Matriz A1", cnpj=cnpj_filial
    )

    with pytest.raises(IntegrityError, match="estabelecimento_cnpj_unico_por_escritorio"):
        with transaction.atomic():
            Estabelecimento.objects.create(
                empresa=empresa_a2,
                tipo=TipoEstabelecimento.MATRIZ,
                nome="Matriz A2",
                cnpj=cnpj_filial,
            )

    # Em outro escritório, o MESMO CNPJ de estabelecimento é aceito.
    Estabelecimento.objects.create(
        empresa=empresa_b, tipo=TipoEstabelecimento.MATRIZ, nome="Matriz B", cnpj=cnpj_filial
    )
    assert Estabelecimento.objects.filter(cnpj=cnpj_filial).count() == 2


def test_bulk_create_de_estabelecimento_e_sincronizado_pelo_gatilho_de_banco(escritorio_a):
    # Achado do plano (critério 2): `bulk_create` não passa por `save()` —
    # sem o gatilho de sincronização (migração 0012), `escritorio_id`
    # ficaria como veio (aqui, deliberadamente ERRADO/None), e a
    # UniqueConstraint por escritório perderia sentido. Só funciona em
    # PostgreSQL — ver a nota de limite de SQLite no comentário da
    # migração e no `test_dl041_gatilho_sqlite.py`.
    escritorio_a_obj, _ = escritorio_a
    empresa = Empresa.objects.create(
        escritorio=escritorio_a_obj, razao_social="Empresa Bulk Ltda", cnpj="11122233000183"
    )

    Estabelecimento.objects.bulk_create(
        [
            Estabelecimento(
                empresa=empresa,
                tipo=TipoEstabelecimento.MATRIZ,
                nome="Matriz Bulk",
                cnpj="AB123CDE000155",
                # escritorio_id NÃO informado de propósito — o gatilho tem
                # que preencher, `bulk_create` nunca chama `save()`.
            )
        ]
    )

    estabelecimento = Estabelecimento.objects.get(cnpj="AB123CDE000155")
    assert estabelecimento.escritorio_id == escritorio_a_obj.pk


# --- Concorrência real: duas conexões inserindo o MESMO CNPJ ao mesmo -----
# tempo (não simulação com monkeypatch) — pedido explícito do plano.


@pytest.mark.django_db(transaction=True)
def test_corrida_real_de_estabelecimento_com_mesmo_cnpj_no_mesmo_escritorio_uma_recusa():
    import threading

    from django.db import connection

    escritorio = Escritorio.objects.create(nome="Escritório Corrida DL-041", cnpj="91100000000103")
    empresa_1 = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Corrida 1 Ltda", cnpj="11122233000183"
    )
    empresa_2 = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Corrida 2 Ltda", cnpj="44455566000183"
    )
    cnpj_disputado = "AB123CDE000155"

    resultados = {}
    erros = {}
    barreira = threading.Barrier(2)

    def _inserir(chave, empresa, nome):
        barreira.wait(timeout=5)
        try:
            with transaction.atomic():
                Estabelecimento.objects.create(
                    empresa=empresa, tipo=TipoEstabelecimento.MATRIZ, nome=nome, cnpj=cnpj_disputado
                )
            resultados[chave] = "sucesso"
        except IntegrityError as exc:
            erros[chave] = exc
        finally:
            connection.close()

    t1 = threading.Thread(target=_inserir, args=("1", empresa_1, "Matriz 1"))
    t2 = threading.Thread(target=_inserir, args=("2", empresa_2, "Matriz 2"))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert len(resultados) == 1, (resultados, erros)
    assert len(erros) == 1, (resultados, erros)
    (excecao,) = erros.values()
    assert "estabelecimento_cnpj_unico_por_escritorio" in str(excecao)
    assert Estabelecimento.objects.filter(cnpj=cnpj_disputado).count() == 1


@pytest.mark.django_db(transaction=True)
def test_corrida_real_de_estabelecimento_com_mesmo_cnpj_em_escritorios_diferentes_as_duas_passam():
    import threading

    from django.db import connection

    escritorio_x = Escritorio.objects.create(
        nome="Escritório Corrida X DL-041", cnpj="91100000000104"
    )
    escritorio_y = Escritorio.objects.create(
        nome="Escritório Corrida Y DL-041", cnpj="91100000000105"
    )
    empresa_x = Empresa.objects.create(
        escritorio=escritorio_x, razao_social="Empresa Corrida X Ltda", cnpj="11122233000183"
    )
    empresa_y = Empresa.objects.create(
        escritorio=escritorio_y, razao_social="Empresa Corrida Y Ltda", cnpj="44455566000183"
    )
    cnpj_compartilhado = "AB123CDE000155"

    resultados = {}
    erros = {}
    barreira = threading.Barrier(2)

    def _inserir(chave, empresa, nome):
        barreira.wait(timeout=5)
        try:
            with transaction.atomic():
                Estabelecimento.objects.create(
                    empresa=empresa,
                    tipo=TipoEstabelecimento.MATRIZ,
                    nome=nome,
                    cnpj=cnpj_compartilhado,
                )
            resultados[chave] = "sucesso"
        except IntegrityError as exc:
            erros[chave] = exc
        finally:
            connection.close()

    t1 = threading.Thread(target=_inserir, args=("x", empresa_x, "Matriz X"))
    t2 = threading.Thread(target=_inserir, args=("y", empresa_y, "Matriz Y"))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert erros == {}, (resultados, erros)
    assert len(resultados) == 2
    assert Estabelecimento.objects.filter(cnpj=cnpj_compartilhado).count() == 2
