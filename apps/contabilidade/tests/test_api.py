from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.contabilidade.models import Conta, NaturezaConta, TipoConta, TipoPartida
from apps.contabilidade.services import criar_lancamento
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


def _usuario_com_papel(papel, escritorio, username):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


@pytest.fixture
def cenario():
    escritorio_a = Escritorio.objects.create(nome="Escritório A", cnpj="11111111000111")
    escritorio_b = Escritorio.objects.create(nome="Escritório B", cnpj="22222222000122")
    empresa_a = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Empresa A Ltda", cnpj="11122233000183"
    )
    empresa_b = Empresa.objects.create(
        escritorio=escritorio_b, razao_social="Empresa B Ltda", cnpj="44455566000183"
    )
    caixa = Conta.objects.create(
        empresa=empresa_a,
        codigo="1.1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    capital = Conta.objects.create(
        empresa=empresa_a,
        codigo="2.1",
        nome="Capital Social",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )
    return {
        "escritorio_a": escritorio_a,
        "escritorio_b": escritorio_b,
        "empresa_a": empresa_a,
        "empresa_b": empresa_b,
        "caixa": caixa,
        "capital": capital,
    }


def test_papel_cliente_nao_pode_criar_lancamento(client, cenario):
    _usuario_com_papel(Papel.CLIENTE, cenario["escritorio_a"], "cliente")
    client.login(username="cliente", password="senha-forte-123")

    response = client.post(
        reverse("contabilidade:lancamentos", args=[cenario["empresa_a"].id]),
        data={
            "data": "2024-01-01",
            "historico": "Tentativa de lançamento",
            "itens": [
                {"conta": cenario["caixa"].id, "tipo": "debito", "valor": "100.00"},
                {"conta": cenario["capital"].id, "tipo": "credito", "valor": "100.00"},
            ],
        },
        content_type="application/json",
    )

    assert response.status_code == 403


def test_papel_gestor_cria_lancamento_balanceado(client, cenario):
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor")
    client.login(username="gestor", password="senha-forte-123")

    response = client.post(
        reverse("contabilidade:lancamentos", args=[cenario["empresa_a"].id]),
        data={
            "data": "2024-01-01",
            "historico": "Integralização de capital",
            "itens": [
                {"conta": cenario["caixa"].id, "tipo": "debito", "valor": "1000.00"},
                {"conta": cenario["capital"].id, "tipo": "credito", "valor": "1000.00"},
            ],
        },
        content_type="application/json",
    )

    assert response.status_code == 201
    assert len(response.json()["itens"]) == 2


def test_lancamento_desbalanceado_retorna_400(client, cenario):
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor")
    client.login(username="gestor", password="senha-forte-123")

    response = client.post(
        reverse("contabilidade:lancamentos", args=[cenario["empresa_a"].id]),
        data={
            "data": "2024-01-01",
            "historico": "Desbalanceado",
            "itens": [
                {"conta": cenario["caixa"].id, "tipo": "debito", "valor": "1000.00"},
                {"conta": cenario["capital"].id, "tipo": "credito", "valor": "900.00"},
            ],
        },
        content_type="application/json",
    )

    assert response.status_code == 400


def test_empresa_de_outro_escritorio_da_404_em_contas(client, cenario):
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor")
    client.login(username="gestor", password="senha-forte-123")

    response = client.get(
        reverse("contabilidade:contas", args=[cenario["empresa_b"].id]),
    )

    assert response.status_code == 404


def test_razao_acumula_saldo_por_conta(client, cenario):
    # Atualizado pela DE-016 (DL-015): a rota passou a EXIGIR 'inicio'/'fim'
    # na querystring, e a resposta deixou de ser {"conta", "saldo_final",
    # "itens"} para o contrato de 4 colunas do plano DL-015 ({"conta",
    # "nome", "inicio", "fim", "saldo_anterior", "total_debito",
    # "total_credito", "saldo_final", "itens"}). O teste original chamava a
    # rota sem período (aceitava o acumulado "desde sempre") — o que a
    # DE-016 deliberadamente proíbe agora.
    usuario = _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor")
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 1),
        historico="Aporte 1",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("1000.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("1000.00")},
        ],
        criado_por=usuario,
    )
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 15),
        historico="Aporte 2",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("500.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("500.00")},
        ],
        criado_por=usuario,
    )
    client.login(username="gestor", password="senha-forte-123")

    response = client.get(
        reverse("contabilidade:razao", args=[cenario["empresa_a"].id, cenario["caixa"].id]),
        {"inicio": "2024-01-01", "fim": "2024-01-31"},
    )

    corpo = response.json()
    assert corpo["saldo_final"] == "1500.00"
    assert [linha["saldo"] for linha in corpo["itens"]] == ["1000.00", "1500.00"]
    # RC-61 / BL-77 (DL-017, fase A): valor sempre absoluto, com indicador de
    # natureza apurada ao lado — Caixa é devedora e não inverte aqui.
    assert corpo["saldo_final_natureza"] == "D"
    assert [linha["saldo_natureza"] for linha in corpo["itens"]] == ["D", "D"]


def test_balancete_reflete_saldos_das_contas(client, cenario):
    # Atualizado pela DE-016 (DL-015): a rota passou a exigir 'inicio'/'fim',
    # e a resposta virou {"inicio", "fim", "contas": [...], "total_debitos",
    # "total_creditos"}, com cada conta trazendo 4 colunas (saldo_anterior,
    # debitos, creditos, saldo_final) em vez da coluna única "saldo".
    usuario = _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor")
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 1),
        historico="Aporte",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("1000.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("1000.00")},
        ],
        criado_por=usuario,
    )
    client.login(username="gestor", password="senha-forte-123")

    response = client.get(
        reverse("contabilidade:balancete", args=[cenario["empresa_a"].id]),
        {"inicio": "2024-01-01", "fim": "2024-01-31"},
    )

    contas_por_codigo = {linha["conta"]: linha for linha in response.json()["contas"]}
    assert contas_por_codigo["1.1"]["saldo_final"] == "1000.00"
    assert contas_por_codigo["2.1"]["saldo_final"] == "1000.00"
    # RC-61 / BL-77 (DL-017, fase A): Caixa (devedora) e Capital (credora)
    # não invertem neste cenário — natureza apurada igual à cadastrada.
    assert contas_por_codigo["1.1"]["saldo_final_natureza"] == "D"
    assert contas_por_codigo["2.1"]["saldo_final_natureza"] == "C"
