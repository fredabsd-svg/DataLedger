"""Testes da DL-015 (onda 1): Diário, Razão e Balancete com período, e a
conferência de lotes desbalanceados.

Cada teste referencia o critério de aceite numerado do plano
docs/planos/DL-015-contabilidade-utilizavel.md. Dados 100% sintéticos,
criados nos próprios testes (nenhum dado real de cliente).
"""

import json
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.contabilidade.models import (
    Conta,
    ItemLancamento,
    LancamentoContabil,
    NaturezaConta,
    TipoConta,
    TipoPartida,
)
from apps.contabilidade.services import criar_lancamento, estornar_lancamento
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


def _usuario_com_papel(papel, escritorio, username):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _autenticar(client, escritorio, username="gestor"):
    _usuario_com_papel(Papel.GESTOR, escritorio, username)
    client.login(username=username, password="senha-forte-123")


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


@pytest.fixture
def cenario_hierarquico():
    """Plano de contas com 3 níveis, para o critério 8 (soma de sintéticas).

    Ativo (nível 1, sintética)
      └── Circulante (nível 2, sintética)
            ├── Caixa (nível 3, analítica)
            └── Bancos (nível 3, analítica)
    """
    escritorio = Escritorio.objects.create(nome="Escritório H", cnpj="33333333000133")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa H Ltda", cnpj="77788899000100"
    )
    ativo = Conta.objects.create(
        empresa=empresa,
        codigo="1",
        nome="Ativo",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        aceita_lancamento=False,
    )
    circulante = Conta.objects.create(
        empresa=empresa,
        codigo="1.1",
        nome="Circulante",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        aceita_lancamento=False,
        conta_pai=ativo,
    )
    caixa = Conta.objects.create(
        empresa=empresa,
        codigo="1.1.01",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        conta_pai=circulante,
    )
    bancos = Conta.objects.create(
        empresa=empresa,
        codigo="1.1.02",
        nome="Bancos",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        conta_pai=circulante,
    )
    capital = Conta.objects.create(
        empresa=empresa,
        codigo="2.1",
        nome="Capital Social",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )
    return {
        "escritorio": escritorio,
        "empresa": empresa,
        "ativo": ativo,
        "circulante": circulante,
        "caixa": caixa,
        "bancos": bancos,
        "capital": capital,
    }


# ---------------------------------------------------------------------------
# Critério 1 — isolamento entre empresas de escritórios diferentes
# ---------------------------------------------------------------------------


def test_diario_de_empresa_de_outro_escritorio_da_404(client, cenario):
    _autenticar(client, cenario["escritorio_a"])

    response = client.get(
        reverse("contabilidade:diario", args=[cenario["empresa_b"].id]),
        {"inicio": "2024-01-01", "fim": "2024-01-31"},
    )

    assert response.status_code == 404


def test_razao_de_empresa_de_outro_escritorio_da_404(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    conta_empresa_b = Conta.objects.create(
        empresa=cenario["empresa_b"],
        codigo="1.1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )

    response = client.get(
        reverse("contabilidade:razao", args=[cenario["empresa_b"].id, conta_empresa_b.id]),
        {"inicio": "2024-01-01", "fim": "2024-01-31"},
    )

    assert response.status_code == 404


def test_balancete_de_empresa_de_outro_escritorio_da_404(client, cenario):
    _autenticar(client, cenario["escritorio_a"])

    response = client.get(
        reverse("contabilidade:balancete", args=[cenario["empresa_b"].id]),
        {"inicio": "2024-01-01", "fim": "2024-01-31"},
    )

    assert response.status_code == 404


def test_conferencia_de_empresa_de_outro_escritorio_da_404(client, cenario):
    _autenticar(client, cenario["escritorio_a"])

    response = client.get(
        reverse("contabilidade:conferencia-lotes-desbalanceados", args=[cenario["empresa_b"].id])
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Critério 2 — validação de período: ausente, malformado, invertido -> 400
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"inicio": "2024-01-01"},
        {"fim": "2024-01-31"},
        {"inicio": "31/01/2024", "fim": "2024-01-31"},
        {"inicio": "abc", "fim": "2024-01-31"},
        {"inicio": "2024-01-31", "fim": "2024-01-01"},  # invertido
    ],
)
def test_diario_com_periodo_invalido_retorna_400(client, cenario, params):
    _autenticar(client, cenario["escritorio_a"])

    response = client.get(reverse("contabilidade:diario", args=[cenario["empresa_a"].id]), params)

    assert response.status_code == 400


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"inicio": "2024-01-01"},
        {"inicio": "31/01/2024", "fim": "2024-01-31"},
        {"inicio": "2024-01-31", "fim": "2024-01-01"},
    ],
)
def test_razao_com_periodo_invalido_retorna_400(client, cenario, params):
    _autenticar(client, cenario["escritorio_a"])

    response = client.get(
        reverse("contabilidade:razao", args=[cenario["empresa_a"].id, cenario["caixa"].id]), params
    )

    assert response.status_code == 400


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"inicio": "2024-01-01"},
        {"inicio": "abc", "fim": "2024-01-31"},
        {"inicio": "2024-01-31", "fim": "2024-01-01"},
    ],
)
def test_balancete_com_periodo_invalido_retorna_400(client, cenario, params):
    _autenticar(client, cenario["escritorio_a"])

    response = client.get(
        reverse("contabilidade:balancete", args=[cenario["empresa_a"].id]), params
    )

    assert response.status_code == 400


def test_balancete_com_nivel_invalido_retorna_400(client, cenario):
    _autenticar(client, cenario["escritorio_a"])

    response = client.get(
        reverse("contabilidade:balancete", args=[cenario["empresa_a"].id]),
        {"inicio": "2024-01-01", "fim": "2024-01-31", "nivel": "0"},
    )

    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Critério 3 — saldo_anterior a partir dos lançamentos anteriores a `inicio`
# ---------------------------------------------------------------------------


def test_razao_apura_saldo_anterior_e_saldo_parte_dele(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2023, 12, 20),  # antes do período consultado
        historico="Aporte anterior ao período",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("500.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("500.00")},
        ],
    )
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 5),  # dentro do período
        historico="Venda à vista",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("300.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("300.00")},
        ],
    )

    response = client.get(
        reverse("contabilidade:razao", args=[cenario["empresa_a"].id, cenario["caixa"].id]),
        {"inicio": "2024-01-01", "fim": "2024-01-31"},
    )

    corpo = response.json()
    assert corpo["saldo_anterior"] == "500.00"
    # A coluna "saldo" acumula A PARTIR do saldo anterior, não de zero.
    assert corpo["itens"][0]["saldo"] == "800.00"
    assert corpo["saldo_final"] == "800.00"


# ---------------------------------------------------------------------------
# Critério 4 — Balancete: saldo_final = saldo_anterior ± (debitos-creditos)
# ---------------------------------------------------------------------------


def test_balancete_saldo_final_respeita_natureza_da_conta(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    # Conta CREDORA (Capital Social): o crédito AUMENTA o saldo, o débito
    # reduz — o inverso da conta devedora. Um bug que sempre fizesse
    # "debito - credito" (ignorando a natureza) produziria aqui um saldo com
    # o SINAL ERRADO, e este teste morre.
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2023, 12, 20),
        historico="Aporte anterior ao período",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("200.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("200.00")},
        ],
    )
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 10),
        historico="Novo aporte no período",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("100.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("100.00")},
        ],
    )

    response = client.get(
        reverse("contabilidade:balancete", args=[cenario["empresa_a"].id]),
        {"inicio": "2024-01-01", "fim": "2024-01-31"},
    )

    linhas = {linha["conta"]: linha for linha in response.json()["contas"]}
    capital = linhas["2.1"]
    assert capital["saldo_anterior"] == "200.00"
    assert capital["debitos"] == "0.00"
    assert capital["creditos"] == "100.00"
    assert capital["saldo_final"] == "300.00"  # 200,00 + (100,00 crédito - 0 débito)

    caixa = linhas["1.1"]
    assert caixa["saldo_anterior"] == "200.00"
    assert caixa["debitos"] == "100.00"
    assert caixa["creditos"] == "0.00"
    assert caixa["saldo_final"] == "300.00"  # 200,00 + (100,00 débito - 0 crédito)


# ---------------------------------------------------------------------------
# Critério 5 — total_debitos == total_creditos no Balancete
# ---------------------------------------------------------------------------


def test_balancete_total_debitos_igual_total_creditos(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 5),
        historico="Aporte",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("1234.56")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("1234.56")},
        ],
    )

    response = client.get(
        reverse("contabilidade:balancete", args=[cenario["empresa_a"].id]),
        {"inicio": "2024-01-01", "fim": "2024-01-31"},
    )

    corpo = response.json()
    assert corpo["total_debitos"] == corpo["total_creditos"] == "1234.56"


# ---------------------------------------------------------------------------
# Critério 6 — conciliação Razão x Balancete
# ---------------------------------------------------------------------------


def test_conciliacao_razao_x_balancete(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2023, 12, 20),
        historico="Anterior",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("500.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("500.00")},
        ],
    )
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 5),
        historico="No período",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("300.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("300.00")},
        ],
    )
    periodo = {"inicio": "2024-01-01", "fim": "2024-01-31"}

    razao = client.get(
        reverse("contabilidade:razao", args=[cenario["empresa_a"].id, cenario["caixa"].id]), periodo
    ).json()
    balancete = client.get(
        reverse("contabilidade:balancete", args=[cenario["empresa_a"].id]), periodo
    ).json()
    linha_caixa = next(linha for linha in balancete["contas"] if linha["conta"] == "1.1")

    assert razao["saldo_anterior"] == linha_caixa["saldo_anterior"]
    assert razao["total_debito"] == linha_caixa["debitos"]
    assert razao["total_credito"] == linha_caixa["creditos"]
    assert razao["saldo_final"] == linha_caixa["saldo_final"]


# ---------------------------------------------------------------------------
# Critério 7 — conciliação Diário x Balancete
# ---------------------------------------------------------------------------


def test_conciliacao_diario_x_balancete(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 5),
        historico="Lançamento 1",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("300.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("300.00")},
        ],
    )
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 20),
        historico="Lançamento 2",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("150.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("150.00")},
        ],
    )
    periodo = {"inicio": "2024-01-01", "fim": "2024-01-31"}

    diario = client.get(
        reverse("contabilidade:diario", args=[cenario["empresa_a"].id]), periodo
    ).json()
    balancete = client.get(
        reverse("contabilidade:balancete", args=[cenario["empresa_a"].id]), periodo
    ).json()

    assert diario["total_debito"] == balancete["total_debitos"] == "450.00"
    assert diario["total_credito"] == balancete["total_creditos"] == "450.00"


# ---------------------------------------------------------------------------
# Critério 8 — sintética soma exatamente as analíticas subordinadas (3 níveis)
# ---------------------------------------------------------------------------


def test_conta_sintetica_soma_exatamente_as_analiticas_subordinadas(client, cenario_hierarquico):
    h = cenario_hierarquico
    _autenticar(client, h["escritorio"])
    criar_lancamento(
        empresa=h["empresa"],
        data=date(2024, 1, 5),
        historico="Depósito em caixa",
        itens=[
            {"conta": h["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("100.00")},
            {"conta": h["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("100.00")},
        ],
    )
    criar_lancamento(
        empresa=h["empresa"],
        data=date(2024, 1, 10),
        historico="Depósito em banco",
        itens=[
            {"conta": h["bancos"], "tipo": TipoPartida.DEBITO, "valor": Decimal("250.00")},
            {"conta": h["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("250.00")},
        ],
    )

    response = client.get(
        reverse("contabilidade:balancete", args=[h["empresa"].id]),
        {"inicio": "2024-01-01", "fim": "2024-01-31"},
    )
    linhas = {linha["conta"]: linha for linha in response.json()["contas"]}

    # Circulante (nível 2) = Caixa + Bancos, exatamente — nem mais, nem menos.
    assert linhas["1.1"]["debitos"] == "350.00"
    assert linhas["1.1"]["saldo_final"] == "350.00"
    assert linhas["1.1"]["analitica"] is False
    assert linhas["1.1"]["nivel"] == 2

    # Ativo (nível 1) = Circulante = Caixa + Bancos — a soma NÃO pode contar
    # o Circulante E as analíticas separadamente (isso dobraria o valor e o
    # total ainda "fecharia", exatamente o erro que o critério 3 do plano
    # avisa para não deixar passar).
    assert linhas["1"]["debitos"] == "350.00"
    assert linhas["1"]["saldo_final"] == "350.00"
    assert linhas["1"]["nivel"] == 1

    # O total geral soma só as analíticas (Caixa 100 + Bancos 250), nunca as
    # sintéticas — se somasse todas, o total seria 350+350+100+250=1050, e
    # ainda assim "bateria" com o crédito de 350 contado em dobro no lado do
    # capital... este teste prova que NÃO é isso que acontece.
    assert response.json()["total_debitos"] == "350.00"
    assert response.json()["total_creditos"] == "350.00"


def test_balancete_com_nivel_corta_analiticas_mas_totais_continuam_completos(
    client, cenario_hierarquico
):
    h = cenario_hierarquico
    _autenticar(client, h["escritorio"])
    criar_lancamento(
        empresa=h["empresa"],
        data=date(2024, 1, 5),
        historico="Depósito em caixa",
        itens=[
            {"conta": h["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("100.00")},
            {"conta": h["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("100.00")},
        ],
    )

    response = client.get(
        reverse("contabilidade:balancete", args=[h["empresa"].id]),
        {"inicio": "2024-01-01", "fim": "2024-01-31", "nivel": "2"},
    )
    corpo = response.json()
    codigos = {linha["conta"] for linha in corpo["contas"]}

    # Nível 3 (Caixa, Bancos) fica de fora da LISTA...
    assert "1.1.01" not in codigos
    assert "1" in codigos and "1.1" in codigos and "2.1" in codigos
    # ...mas o TOTAL continua completo (o parâmetro só filtra exibição).
    assert corpo["total_debitos"] == "100.00"
    assert corpo["total_creditos"] == "100.00"


# ---------------------------------------------------------------------------
# Critério 9 — conferência encontra lote desbalanceado gravado fora do serviço
# ---------------------------------------------------------------------------


def test_conferencia_encontra_lote_desbalanceado_gravado_via_orm(client, cenario):
    # `criar_lancamento` corretamente IMPEDE um lote desbalanceado — é por
    # isso que o cenário deste teste precisa contornar o serviço e gravar
    # direto pelo ORM (LancamentoContabil.objects.create +
    # ItemLancamento.objects.create). É legítimo apenas aqui: simula um
    # lançamento gravado por um caminho que não passa pela validação
    # contábil (ex.: migração de dados ou bug futuro) — exatamente o que a
    # rota de conferência existe para achar.
    _autenticar(client, cenario["escritorio_a"])
    lote_torto = LancamentoContabil.objects.create(
        empresa=cenario["empresa_a"], data=date(2024, 1, 9), historico="Ajuste torto"
    )
    ItemLancamento.objects.create(
        lancamento=lote_torto,
        conta=cenario["caixa"],
        tipo=TipoPartida.DEBITO,
        valor=Decimal("100.00"),
    )
    ItemLancamento.objects.create(
        lancamento=lote_torto,
        conta=cenario["capital"],
        tipo=TipoPartida.CREDITO,
        valor=Decimal("90.00"),
    )
    # Lançamento balanceado, criado normalmente, não deve aparecer.
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 10),
        historico="Lançamento correto",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("50.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("50.00")},
        ],
    )

    response = client.get(
        reverse("contabilidade:conferencia-lotes-desbalanceados", args=[cenario["empresa_a"].id])
    )

    lotes = response.json()["lotes"]
    assert len(lotes) == 1
    assert lotes[0]["id"] == lote_torto.id
    assert lotes[0]["total_debito"] == "100.00"
    assert lotes[0]["total_credito"] == "90.00"
    assert lotes[0]["diferenca"] == "10.00"


def test_conferencia_em_base_sadia_devolve_lista_vazia(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 10),
        historico="Lançamento correto",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("50.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("50.00")},
        ],
    )

    response = client.get(
        reverse("contabilidade:conferencia-lotes-desbalanceados", args=[cenario["empresa_a"].id])
    )

    assert response.json()["lotes"] == []


# ---------------------------------------------------------------------------
# Critério 10 — bordas do intervalo: inclusivas nos dois extremos
# ---------------------------------------------------------------------------


def test_lancamento_exatamente_em_inicio_e_em_fim_entram_no_periodo(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 1),  # exatamente no início
        historico="No início",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("10.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("10.00")},
        ],
    )
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 31),  # exatamente no fim
        historico="No fim",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("20.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("20.00")},
        ],
    )
    periodo = {"inicio": "2024-01-01", "fim": "2024-01-31"}

    diario = client.get(
        reverse("contabilidade:diario", args=[cenario["empresa_a"].id]), periodo
    ).json()
    assert len(diario["lancamentos"]) == 2
    assert diario["total_debito"] == "30.00"

    balancete = client.get(
        reverse("contabilidade:balancete", args=[cenario["empresa_a"].id]), periodo
    ).json()
    linha_caixa = next(linha for linha in balancete["contas"] if linha["conta"] == "1.1")
    assert linha_caixa["debitos"] == "30.00"


def test_lancamento_fora_do_intervalo_nao_aparece_em_nenhuma_saida_nem_totais(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 2, 1),  # um dia depois do fim do período consultado
        historico="Fora do período",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("999.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("999.00")},
        ],
    )
    periodo = {"inicio": "2024-01-01", "fim": "2024-01-31"}

    diario = client.get(
        reverse("contabilidade:diario", args=[cenario["empresa_a"].id]), periodo
    ).json()
    assert diario["lancamentos"] == []
    assert diario["total_debito"] == "0.00"

    razao = client.get(
        reverse("contabilidade:razao", args=[cenario["empresa_a"].id, cenario["caixa"].id]),
        periodo,
    ).json()
    assert razao["itens"] == []
    assert razao["saldo_final"] == "0.00"
    assert razao["saldo_anterior"] == "0.00"  # também não é "anterior": é POSTERIOR ao período

    balancete = client.get(
        reverse("contabilidade:balancete", args=[cenario["empresa_a"].id]), periodo
    ).json()
    linha_caixa = next(linha for linha in balancete["contas"] if linha["conta"] == "1.1")
    assert linha_caixa["debitos"] == "0.00"
    assert linha_caixa["saldo_final"] == "0.00"
    assert balancete["total_debitos"] == "0.00"


# ---------------------------------------------------------------------------
# Critério 11 — estorno aparece como lançamento próprio; par soma zero
# ---------------------------------------------------------------------------


def test_estorno_aparece_como_lancamento_proprio_e_par_soma_zero_no_periodo(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    original = criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 5),
        historico="Lançamento original",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("500.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("500.00")},
        ],
    )
    estorno = estornar_lancamento(original, data=date(2024, 1, 10))
    periodo = {"inicio": "2024-01-01", "fim": "2024-01-31"}

    diario = client.get(
        reverse("contabilidade:diario", args=[cenario["empresa_a"].id]), periodo
    ).json()
    ids = {lancamento["id"] for lancamento in diario["lancamentos"]}
    datas = {lancamento["id"]: lancamento["data"] for lancamento in diario["lancamentos"]}
    assert ids == {original.id, estorno.id}
    assert datas[estorno.id] == "2024-01-10"  # o estorno aparece NA DATA DELE, não na do original

    razao = client.get(
        reverse("contabilidade:razao", args=[cenario["empresa_a"].id, cenario["caixa"].id]),
        periodo,
    ).json()
    # O par original + estorno se cancela: saldo final do período é zero.
    assert razao["saldo_final"] == "0.00"
    assert len(razao["itens"]) == 2


# ---------------------------------------------------------------------------
# Critério 12 — sem N+1 no Balancete
# ---------------------------------------------------------------------------


def test_balancete_numero_de_consultas_nao_cresce_com_numero_de_contas(client, cenario):
    """Antes desta etapa, o Balancete fazia DUAS consultas POR CONTA (um Sum
    de débito e um de crédito para cada). A versão desta etapa agrega tudo
    numa única consulta agregada por conta (`values("conta").annotate(...)`),
    então o número de consultas da requisição deve ser o MESMO com 3 contas
    e com 30 — não crescer linearmente. Medido por contagem real de
    consultas (CaptureQueriesContext), não por um número fixo — o que
    importa é a IGUALDADE entre os dois cenários, não um valor absoluto que
    ficaria frágil a mudanças de autenticação/middleware sem relação com
    este critério.
    """
    _autenticar(client, cenario["escritorio_a"])
    empresa = cenario["empresa_a"]
    periodo = {"inicio": "2024-01-01", "fim": "2024-01-31"}

    # Aquecimento (fora da medição): a PRIMEIRA requisição autenticada do
    # teste paga consultas de sessão/permissão que não se repetem nas
    # seguintes (cache de sessão, ContentType etc.) — sem isto, a contagem
    # cairia entre a 1ª e a 2ª chamada por um motivo que nada tem a ver com
    # o critério 12 (N+1 no Balancete), mascarando o que este teste mede.
    client.get(reverse("contabilidade:balancete", args=[empresa.id]), periodo)

    def _criar_contas_com_lancamento(quantidade, prefixo):
        for i in range(quantidade):
            conta = Conta.objects.create(
                empresa=empresa,
                codigo=f"{prefixo}.{i}",
                nome=f"Conta {prefixo}-{i}",
                tipo=TipoConta.ATIVO,
                natureza=NaturezaConta.DEVEDORA,
            )
            criar_lancamento(
                empresa=empresa,
                data=date(2024, 1, 15),
                historico="Movimento de teste",
                itens=[
                    {"conta": conta, "tipo": TipoPartida.DEBITO, "valor": Decimal("10.00")},
                    {
                        "conta": cenario["capital"],
                        "tipo": TipoPartida.CREDITO,
                        "valor": Decimal("10.00"),
                    },
                ],
            )

    _criar_contas_com_lancamento(3, "9")
    with CaptureQueriesContext(connection) as consultas_com_poucas_contas:
        resposta_pequena = client.get(
            reverse("contabilidade:balancete", args=[empresa.id]), periodo
        )
    assert resposta_pequena.status_code == 200

    _criar_contas_com_lancamento(27, "8")  # total: 30 contas na empresa
    with CaptureQueriesContext(connection) as consultas_com_muitas_contas:
        resposta_grande = client.get(reverse("contabilidade:balancete", args=[empresa.id]), periodo)
    assert resposta_grande.status_code == 200
    assert len(resposta_grande.json()["contas"]) > len(resposta_pequena.json()["contas"])

    assert len(consultas_com_muitas_contas) == len(consultas_com_poucas_contas)


# ---------------------------------------------------------------------------
# Critério 13 — valores monetários sempre como string, nunca float no JSON
# ---------------------------------------------------------------------------


def _falhar_se_algum_numero_chegar_como_float(texto):
    raise AssertionError(
        f"Um valor chegou ao JSON como número de ponto flutuante, não como "
        f"string: {texto!r}. Todo valor monetário tem que ser string com "
        "duas casas decimais (AGENTS.md, seção 10)."
    )


def test_valores_monetarios_sao_sempre_string_no_json_cru(client, cenario):
    """Usa `json.loads(..., parse_float=...)`: se ALGUM token numérico do
    JSON cru tiver ponto decimal (ou notação científica), o parser chama o
    callback em vez de construir um `float` — e o callback falha o teste.
    IDs e "nivel" são inteiros simples (sem ponto), então não disparam o
    callback; só um valor monetário vazando sem aspas dispararia.
    """
    _autenticar(client, cenario["escritorio_a"])
    original = criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 5),
        historico="Lançamento",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("1234.56")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("1234.56")},
        ],
    )
    estornar_lancamento(original, data=date(2024, 1, 6))
    periodo = {"inicio": "2024-01-01", "fim": "2024-01-31"}

    rotas = [
        reverse("contabilidade:diario", args=[cenario["empresa_a"].id]),
        reverse("contabilidade:razao", args=[cenario["empresa_a"].id, cenario["caixa"].id]),
        reverse("contabilidade:balancete", args=[cenario["empresa_a"].id]),
    ]
    for rota in rotas:
        response = client.get(rota, periodo)
        assert response.status_code == 200
        json.loads(response.content, parse_float=_falhar_se_algum_numero_chegar_como_float)

    response = client.get(
        reverse("contabilidade:conferencia-lotes-desbalanceados", args=[cenario["empresa_a"].id])
    )
    assert response.status_code == 200
    json.loads(response.content, parse_float=_falhar_se_algum_numero_chegar_como_float)
