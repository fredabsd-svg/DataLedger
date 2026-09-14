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
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.core.exceptions import ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.contabilidade.models import (
    Conta,
    ItemLancamento,
    LancamentoContabil,
    NaturezaConta,
    TipoConta,
    TipoPartida,
)
from apps.contabilidade.services import criar_lancamento, estornar_lancamento, listar_diario
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
    # Contas da empresa B (outro escritório) — usadas pelos testes de
    # isolamento de CONTEÚDO (achado 1 da auditoria DL-015, rodada 1): não
    # basta o 404 de empresa errada, é preciso provar que nenhum dado da
    # empresa B aparece na resposta da empresa A.
    caixa_b = Conta.objects.create(
        empresa=empresa_b,
        codigo="1.1",
        nome="Caixa Cliente B",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    capital_b = Conta.objects.create(
        empresa=empresa_b,
        codigo="2.1",
        nome="Capital Cliente B",
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
        "caixa_b": caixa_b,
        "capital_b": capital_b,
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
    # "caixa_b" já existe na fixture `cenario` (empresa B, outro escritório);
    # reaproveitada em vez de criar outra conta com o mesmo código, o que
    # colidiria com a constraint `codigo_unico_por_empresa`.

    response = client.get(
        reverse("contabilidade:razao", args=[cenario["empresa_b"].id, cenario["caixa_b"].id]),
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
    # RC-61 / BL-77: Caixa é devedora e nunca inverte de lado neste cenário
    # (só débito) — a natureza APURADA coincide com a CADASTRADA em todo
    # ponto, e o valor já vem em módulo (positivo), nunca negativo.
    assert corpo["saldo_anterior_natureza"] == "D"
    assert corpo["itens"][0]["saldo_natureza"] == "D"
    assert corpo["saldo_final_natureza"] == "D"


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
    # RC-61 / BL-77: Capital é CREDORA e todo o movimento é a favor do lado
    # cadastrado — natureza apurada "C" em todo ponto.
    assert capital["saldo_anterior_natureza"] == "C"
    assert capital["saldo_final_natureza"] == "C"

    caixa = linhas["1.1"]
    assert caixa["saldo_anterior"] == "200.00"
    assert caixa["debitos"] == "100.00"
    assert caixa["creditos"] == "0.00"
    assert caixa["saldo_final"] == "300.00"  # 200,00 + (100,00 débito - 0 crédito)
    # Caixa é DEVEDORA, também sem inversão neste cenário — natureza "D".
    assert caixa["saldo_anterior_natureza"] == "D"
    assert caixa["saldo_final_natureza"] == "D"


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
    # RC-61 / BL-77: a conciliação também vale para a natureza apurada — as
    # duas saídas descrevem a MESMA conta, no MESMO período, então o
    # indicador D/C tem que bater, não só o número absoluto.
    assert razao["saldo_anterior_natureza"] == linha_caixa["saldo_anterior_natureza"]
    assert razao["saldo_final_natureza"] == linha_caixa["saldo_final_natureza"]


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
    # RC-61 / BL-77: saldo ZERO não tem lado — nem D nem C. `letra=None` é
    # decisão explícita de `_saldo_absoluto_com_natureza` (views.py).
    assert razao["saldo_final_natureza"] is None
    assert razao["saldo_anterior_natureza"] is None

    balancete = client.get(
        reverse("contabilidade:balancete", args=[cenario["empresa_a"].id]), periodo
    ).json()
    linha_caixa = next(linha for linha in balancete["contas"] if linha["conta"] == "1.1")
    assert linha_caixa["debitos"] == "0.00"
    assert linha_caixa["saldo_final"] == "0.00"
    assert linha_caixa["saldo_final_natureza"] is None
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


# ===========================================================================
# Testes da auditoria da DL-015, rodada 1 (docs/auditorias/2026-09-13-dl-015-
# rodada-1.md), reprovada. Cada bloco abaixo referencia o número do achado.
# ===========================================================================


# ---------------------------------------------------------------------------
# Achado 1 — isolamento de CONTEÚDO entre escritórios (não só o 404)
# ---------------------------------------------------------------------------


def test_diario_isolamento_de_conteudo_entre_escritorios(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 5),
        historico="Movimento de A",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("100.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("100.00")},
        ],
    )
    criar_lancamento(
        empresa=cenario["empresa_b"],
        data=date(2024, 1, 5),
        historico="SEGREDO do cliente de B",
        itens=[
            {"conta": cenario["caixa_b"], "tipo": TipoPartida.DEBITO, "valor": Decimal("7777.77")},
            {
                "conta": cenario["capital_b"],
                "tipo": TipoPartida.CREDITO,
                "valor": Decimal("7777.77"),
            },
        ],
    )

    response = client.get(
        reverse("contabilidade:diario", args=[cenario["empresa_a"].id]),
        {"inicio": "2024-01-01", "fim": "2024-01-31"},
    )

    corpo_bruto = response.content.decode()
    assert "SEGREDO" not in corpo_bruto
    assert "7777.77" not in corpo_bruto
    assert "Caixa Cliente B" not in corpo_bruto
    corpo = response.json()
    assert len(corpo["lancamentos"]) == 1
    assert corpo["total_debito"] == corpo["total_credito"] == "100.00"


def test_razao_isolamento_de_conteudo_entre_escritorios(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 5),
        historico="Movimento de A",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("100.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("100.00")},
        ],
    )
    criar_lancamento(
        empresa=cenario["empresa_b"],
        data=date(2024, 1, 5),
        historico="SEGREDO do cliente de B",
        itens=[
            {"conta": cenario["caixa_b"], "tipo": TipoPartida.DEBITO, "valor": Decimal("7777.77")},
            {
                "conta": cenario["capital_b"],
                "tipo": TipoPartida.CREDITO,
                "valor": Decimal("7777.77"),
            },
        ],
    )

    response = client.get(
        reverse("contabilidade:razao", args=[cenario["empresa_a"].id, cenario["caixa"].id]),
        {"inicio": "2024-01-01", "fim": "2024-01-31"},
    )

    corpo_bruto = response.content.decode()
    assert "SEGREDO" not in corpo_bruto
    assert "7777.77" not in corpo_bruto
    corpo = response.json()
    assert corpo["saldo_final"] == "100.00"
    assert len(corpo["itens"]) == 1


def test_razao_com_conta_de_outra_empresa_mas_empresa_id_legitimo_da_404(client, cenario):
    # Evidência que faltava (achado 1): `empresa_id` da URL é da empresa A
    # (legítima, do escritório do usuário), mas `conta_id` pertence à
    # empresa B. Hoje já dá 404 (get_object_or_404 filtra por empresa), mas
    # não havia teste nenhum provando isto.
    _autenticar(client, cenario["escritorio_a"])

    response = client.get(
        reverse("contabilidade:razao", args=[cenario["empresa_a"].id, cenario["caixa_b"].id]),
        {"inicio": "2024-01-01", "fim": "2024-01-31"},
    )

    assert response.status_code == 404


def test_balancete_isolamento_de_conteudo_entre_escritorios(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 5),
        historico="Movimento de A",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("100.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("100.00")},
        ],
    )
    criar_lancamento(
        empresa=cenario["empresa_b"],
        data=date(2024, 1, 5),
        historico="SEGREDO do cliente de B",
        itens=[
            {"conta": cenario["caixa_b"], "tipo": TipoPartida.DEBITO, "valor": Decimal("7777.77")},
            {
                "conta": cenario["capital_b"],
                "tipo": TipoPartida.CREDITO,
                "valor": Decimal("7777.77"),
            },
        ],
    )

    response = client.get(
        reverse("contabilidade:balancete", args=[cenario["empresa_a"].id]),
        {"inicio": "2024-01-01", "fim": "2024-01-31"},
    )

    corpo_bruto = response.content.decode()
    assert "SEGREDO" not in corpo_bruto
    assert "7777.77" not in corpo_bruto
    assert "Caixa Cliente B" not in corpo_bruto
    assert "Capital Cliente B" not in corpo_bruto
    corpo = response.json()
    assert {linha["conta"] for linha in corpo["contas"]} == {"1.1", "2.1"}
    assert corpo["total_debitos"] == corpo["total_creditos"] == "100.00"


def test_conferencia_isolamento_de_conteudo_entre_escritorios(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    lote_a = LancamentoContabil.objects.create(
        empresa=cenario["empresa_a"], data=date(2024, 1, 9), historico="Ajuste torto A"
    )
    ItemLancamento.objects.create(
        lancamento=lote_a, conta=cenario["caixa"], tipo=TipoPartida.DEBITO, valor=Decimal("100.00")
    )
    ItemLancamento.objects.create(
        lancamento=lote_a,
        conta=cenario["capital"],
        tipo=TipoPartida.CREDITO,
        valor=Decimal("90.00"),
    )
    lote_b = LancamentoContabil.objects.create(
        empresa=cenario["empresa_b"], data=date(2024, 1, 9), historico="SEGREDO desbalanceado B"
    )
    ItemLancamento.objects.create(
        lancamento=lote_b,
        conta=cenario["caixa_b"],
        tipo=TipoPartida.DEBITO,
        valor=Decimal("7777.77"),
    )
    ItemLancamento.objects.create(
        lancamento=lote_b,
        conta=cenario["capital_b"],
        tipo=TipoPartida.CREDITO,
        valor=Decimal("1.00"),
    )

    response = client.get(
        reverse("contabilidade:conferencia-lotes-desbalanceados", args=[cenario["empresa_a"].id])
    )

    corpo_bruto = response.content.decode()
    assert "SEGREDO" not in corpo_bruto
    assert "7777.77" not in corpo_bruto
    lotes = response.json()["lotes"]
    assert len(lotes) == 1
    assert lotes[0]["id"] == lote_a.id


# ---------------------------------------------------------------------------
# Achados 2 e 7 — regra única de saldo (DE-020): movimento próprio +
# descendentes, para QUALQUER conta, independente de aceita_lancamento
# ---------------------------------------------------------------------------


def test_balancete_conta_reclassificada_como_sintetica_com_movimento_nao_perde_valor(
    client, cenario
):
    # Reprodução do achado 2: conta analítica recebe lançamento e é
    # reclassificada como sintética POR FORA da validação (ORM direto,
    # `.update()`, que não passa por `Conta.clean()` — a mesma via que a
    # auditoria usou para reproduzir o defeito). A regra única de saldo
    # (DE-020) faz o valor CONTINUAR aparecendo: nem o Balancete perde o
    # débito, nem o total para de bater.
    _autenticar(client, cenario["escritorio_a"])
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 5),
        historico="Lançamento antes da reclassificação",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("500.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("500.00")},
        ],
    )
    Conta.objects.filter(pk=cenario["caixa"].id).update(aceita_lancamento=False)

    response = client.get(
        reverse("contabilidade:balancete", args=[cenario["empresa_a"].id]),
        {"inicio": "2024-01-01", "fim": "2024-01-31"},
    )

    corpo = response.json()
    assert corpo["total_debitos"] == corpo["total_creditos"] == "500.00"
    linha_caixa = next(linha for linha in corpo["contas"] if linha["conta"] == "1.1")
    assert linha_caixa["debitos"] == "500.00"
    assert linha_caixa["saldo_final"] == "500.00"


def test_balancete_conta_analitica_com_filha_soma_proprio_mais_descendente(client, cenario):
    # Reprodução do achado 7: conta ANALÍTICA "3" com movimento PRÓPRIO e
    # filha analítica "3.1" com movimento próprio. A regra única de saldo
    # soma os dois na linha do pai, sem descartar o da filha.
    _autenticar(client, cenario["escritorio_a"])
    pai = Conta.objects.create(
        empresa=cenario["empresa_a"],
        codigo="3",
        nome="Resultado",
        tipo=TipoConta.DESPESA,
        natureza=NaturezaConta.DEVEDORA,
    )
    filha = Conta.objects.create(
        empresa=cenario["empresa_a"],
        codigo="3.1",
        nome="Resultado detalhe",
        tipo=TipoConta.DESPESA,
        natureza=NaturezaConta.DEVEDORA,
        conta_pai=pai,
    )
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 5),
        historico="Movimento do pai",
        itens=[
            {"conta": pai, "tipo": TipoPartida.DEBITO, "valor": Decimal("60.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("60.00")},
        ],
    )
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 10),
        historico="Movimento da filha",
        itens=[
            {"conta": filha, "tipo": TipoPartida.DEBITO, "valor": Decimal("40.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("40.00")},
        ],
    )

    periodo = {"inicio": "2024-01-01", "fim": "2024-01-31"}
    response_sem_nivel = client.get(
        reverse("contabilidade:balancete", args=[cenario["empresa_a"].id]), periodo
    )
    corpo = response_sem_nivel.json()
    linha_pai = next(linha for linha in corpo["contas"] if linha["conta"] == "3")
    assert linha_pai["debitos"] == "100.00"  # 60 (próprio) + 40 (filha) — nada perdido
    assert corpo["total_debitos"] == corpo["total_creditos"] == "100.00"

    # Com nivel=1, a filha "3.1" (nível 2) sai da LISTA exibida, mas o TOTAL
    # continua completo — o parâmetro só filtra exibição (critério 3 do
    # plano), nunca a soma.
    periodo_com_nivel = {**periodo, "nivel": "1"}
    response_com_nivel = client.get(
        reverse("contabilidade:balancete", args=[cenario["empresa_a"].id]), periodo_com_nivel
    )
    corpo_com_nivel = response_com_nivel.json()
    assert "3.1" not in {linha["conta"] for linha in corpo_com_nivel["contas"]}
    assert corpo_com_nivel["total_debitos"] == "100.00"


def test_conta_recusa_reclassificacao_para_sintetica_com_movimento_proprio(cenario):
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 5),
        historico="Lançamento",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("500.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("500.00")},
        ],
    )
    caixa = cenario["caixa"]
    caixa.aceita_lancamento = False

    with pytest.raises(ValidationError):
        caixa.full_clean()


def test_conferencia_aponta_conta_sintetica_com_movimento_proprio(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 5),
        historico="Lançamento",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("500.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("500.00")},
        ],
    )
    Conta.objects.filter(pk=cenario["caixa"].id).update(aceita_lancamento=False)

    response = client.get(
        reverse("contabilidade:conferencia-lotes-desbalanceados", args=[cenario["empresa_a"].id])
    )

    contas = response.json()["contas_sinteticas_com_movimento"]
    assert any(
        c["conta"] == "1.1" and c["debitos"] == "500.00" and c["creditos"] == "0.00" for c in contas
    )


# ---------------------------------------------------------------------------
# Achado 3 — grupo com conta retificadora: natureza do GRUPO aplicada uma
# única vez sobre débitos/créditos brutos das descendentes
# ---------------------------------------------------------------------------


def test_balancete_grupo_com_conta_retificadora_aplica_natureza_do_grupo_uma_vez(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    imobilizado = Conta.objects.create(
        empresa=cenario["empresa_a"],
        codigo="1.2",
        nome="Imobilizado (grupo)",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        aceita_lancamento=False,
    )
    bens = Conta.objects.create(
        empresa=cenario["empresa_a"],
        codigo="1.2.1",
        nome="Bens",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        conta_pai=imobilizado,
    )
    depreciacao = Conta.objects.create(
        empresa=cenario["empresa_a"],
        codigo="1.2.2",
        nome="(-) Depreciação acumulada",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.CREDORA,  # retificadora: natureza OPOSTA ao grupo
        conta_pai=imobilizado,
    )
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 5),
        historico="Aquisição de bem",
        itens=[
            {"conta": bens, "tipo": TipoPartida.DEBITO, "valor": Decimal("100.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("100.00")},
        ],
    )
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 10),
        historico="Depreciação do período",
        itens=[
            {"conta": cenario["capital"], "tipo": TipoPartida.DEBITO, "valor": Decimal("30.00")},
            {"conta": depreciacao, "tipo": TipoPartida.CREDITO, "valor": Decimal("30.00")},
        ],
    )

    response = client.get(
        reverse("contabilidade:balancete", args=[cenario["empresa_a"].id]),
        {"inicio": "2024-01-01", "fim": "2024-01-31"},
    )

    linhas = {linha["conta"]: linha for linha in response.json()["contas"]}
    grupo = linhas["1.2"]
    # 100,00 (débito de Bens) − 30,00 (crédito da retificadora) = 70,00 —
    # nunca 130,00 (soma sem aplicar a natureza do grupo à retificadora).
    assert grupo["debitos"] == "100.00"
    assert grupo["creditos"] == "30.00"
    assert grupo["saldo_final"] == "70.00"
    # RC-61 / BL-77: o grupo é cadastrado DEVEDOR e apura saldo devedor (o
    # crédito da retificadora não é suficiente para inverter o lado) —
    # natureza apurada "D", igual à cadastrada.
    assert grupo["saldo_final_natureza"] == "D"
    depreciacao_linha = linhas["1.2.2"]
    # A retificadora, isolada, é CREDORA e só recebeu crédito — natureza
    # apurada "C", igual à cadastrada (ela não inverte; é o GRUPO que
    # absorve o crédito dela sem inverter, porque o débito de "Bens" é
    # maior).
    assert depreciacao_linha["saldo_final_natureza"] == "C"


def _assert_toda_linha_do_balancete_bate_com_a_propria_natureza(response, empresa):
    """Teste GENÉRICO pedido pelo achado 3, adaptado pela RC-61 / BL-77: para
    TODA linha do balancete, analítica ou sintética, o saldo RECONSTRUÍDO
    (valor absoluto + natureza apurada, convertido de volta para o saldo
    ASSINADO) tem que satisfazer `saldo_final == saldo_anterior ±
    (debitos − creditos)` conforme a NATUREZA CADASTRADA DA PRÓPRIA CONTA
    (nunca a de um filho ou de outra linha) — lida direto do banco, sem
    depender da fixture.

    Reconstruir o saldo assinado a partir de `(valor_absoluto,
    natureza_apurada, natureza_cadastrada)` é o INVERSO exato de
    `views._saldo_absoluto_com_natureza`: positivo quando as duas letras
    coincidem, negativo quando não coincidem, zero quando `natureza_apurada`
    vier `None`. Antes da RC-61/BL-77 este teste comparava o saldo ASSINADO
    direto; agora prova que a conversão para valor absoluto + indicador é
    REVERSÍVEL — não só "parece certa" nos poucos casos escolhidos a dedo
    pelos testes específicos de cada achado.
    """
    naturezas_por_codigo = dict(
        Conta.objects.filter(empresa=empresa).values_list("codigo", "natureza")
    )

    def _assinado(valor_absoluto, natureza_apurada, natureza_cadastrada):
        if natureza_apurada is None:
            assert valor_absoluto == 0
            return Decimal("0")
        letra_cadastrada = "D" if natureza_cadastrada == NaturezaConta.DEVEDORA else "C"
        return valor_absoluto if natureza_apurada == letra_cadastrada else -valor_absoluto

    for linha in response.json()["contas"]:
        natureza_cadastrada = naturezas_por_codigo[linha["conta"]]
        saldo_anterior = _assinado(
            Decimal(linha["saldo_anterior"]), linha["saldo_anterior_natureza"], natureza_cadastrada
        )
        debitos = Decimal(linha["debitos"])
        creditos = Decimal(linha["creditos"])
        saldo_final = _assinado(
            Decimal(linha["saldo_final"]), linha["saldo_final_natureza"], natureza_cadastrada
        )
        sinal = 1 if natureza_cadastrada == NaturezaConta.DEVEDORA else -1
        assert saldo_final == saldo_anterior + sinal * (debitos - creditos), linha


def test_balancete_toda_linha_bate_com_a_propria_natureza_cenario_simples(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 5),
        historico="Movimento",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("77.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("77.00")},
        ],
    )

    response = client.get(
        reverse("contabilidade:balancete", args=[cenario["empresa_a"].id]),
        {"inicio": "2024-01-01", "fim": "2024-01-31"},
    )

    _assert_toda_linha_do_balancete_bate_com_a_propria_natureza(response, cenario["empresa_a"])


def test_balancete_toda_linha_bate_com_a_propria_natureza_cenario_hierarquico(
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

    _assert_toda_linha_do_balancete_bate_com_a_propria_natureza(response, h["empresa"])


def test_balancete_toda_linha_bate_com_a_propria_natureza_com_retificadora(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    imobilizado = Conta.objects.create(
        empresa=cenario["empresa_a"],
        codigo="1.2",
        nome="Imobilizado (grupo)",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        aceita_lancamento=False,
    )
    bens = Conta.objects.create(
        empresa=cenario["empresa_a"],
        codigo="1.2.1",
        nome="Bens",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        conta_pai=imobilizado,
    )
    depreciacao = Conta.objects.create(
        empresa=cenario["empresa_a"],
        codigo="1.2.2",
        nome="(-) Depreciação acumulada",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.CREDORA,
        conta_pai=imobilizado,
    )
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 5),
        historico="Aquisição de bem",
        itens=[
            {"conta": bens, "tipo": TipoPartida.DEBITO, "valor": Decimal("100.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("100.00")},
        ],
    )
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 10),
        historico="Depreciação do período",
        itens=[
            {"conta": cenario["capital"], "tipo": TipoPartida.DEBITO, "valor": Decimal("30.00")},
            {"conta": depreciacao, "tipo": TipoPartida.CREDITO, "valor": Decimal("30.00")},
        ],
    )

    response = client.get(
        reverse("contabilidade:balancete", args=[cenario["empresa_a"].id]),
        {"inicio": "2024-01-01", "fim": "2024-01-31"},
    )

    _assert_toda_linha_do_balancete_bate_com_a_propria_natureza(response, cenario["empresa_a"])


# ---------------------------------------------------------------------------
# Achado 4 — Razão de conta CREDORA: saldo_anterior, coluna saldo, saldo_final
# ---------------------------------------------------------------------------


def test_razao_conta_credora_apura_saldo_anterior_coluna_saldo_e_saldo_final(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2023, 12, 20),
        historico="Aporte anterior ao período",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("500.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("500.00")},
        ],
    )
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 5),
        historico="Novo aporte no período",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("300.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("300.00")},
        ],
    )
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 10),
        historico="Devolução de capital",
        itens=[
            {"conta": cenario["capital"], "tipo": TipoPartida.DEBITO, "valor": Decimal("100.00")},
            {"conta": cenario["caixa"], "tipo": TipoPartida.CREDITO, "valor": Decimal("100.00")},
        ],
    )

    response = client.get(
        reverse("contabilidade:razao", args=[cenario["empresa_a"].id, cenario["capital"].id]),
        {"inicio": "2024-01-01", "fim": "2024-01-31"},
    )

    corpo = response.json()
    # Crédito AUMENTA conta credora; débito REDUZ — o oposto da devedora.
    assert corpo["saldo_anterior"] == "500.00"
    assert [item["saldo"] for item in corpo["itens"]] == ["800.00", "700.00"]
    assert corpo["saldo_final"] == "700.00"
    # RC-61 / BL-77: Capital é CREDORA e o saldo nunca inverte de lado neste
    # cenário (a devolução de 100,00 não é suficiente para zerar os 800,00
    # acumulados) — natureza apurada "C" em todo ponto, igual à cadastrada.
    assert corpo["saldo_anterior_natureza"] == "C"
    assert [item["saldo_natureza"] for item in corpo["itens"]] == ["C", "C"]
    assert corpo["saldo_final_natureza"] == "C"


def test_conciliacao_razao_x_balancete_conta_credora(client, cenario):
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
            {"conta": cenario["capital"], "tipo": TipoPartida.DEBITO, "valor": Decimal("50.00")},
            {"conta": cenario["caixa"], "tipo": TipoPartida.CREDITO, "valor": Decimal("50.00")},
        ],
    )
    periodo = {"inicio": "2024-01-01", "fim": "2024-01-31"}

    razao = client.get(
        reverse("contabilidade:razao", args=[cenario["empresa_a"].id, cenario["capital"].id]),
        periodo,
    ).json()
    balancete = client.get(
        reverse("contabilidade:balancete", args=[cenario["empresa_a"].id]), periodo
    ).json()
    linha_capital = next(linha for linha in balancete["contas"] if linha["conta"] == "2.1")

    assert razao["saldo_anterior"] == linha_capital["saldo_anterior"]
    assert razao["total_debito"] == linha_capital["debitos"]
    assert razao["total_credito"] == linha_capital["creditos"]
    assert razao["saldo_final"] == linha_capital["saldo_final"]
    assert razao["saldo_anterior_natureza"] == linha_capital["saldo_anterior_natureza"]
    assert razao["saldo_final_natureza"] == linha_capital["saldo_final_natureza"]


# ---------------------------------------------------------------------------
# Achado 5 — borda `fim` do Razão; ordenação cronológica; desempate do Diário
# ---------------------------------------------------------------------------


def test_razao_borda_fim_e_inicio_inclusiva(client, cenario):
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

    response = client.get(
        reverse("contabilidade:razao", args=[cenario["empresa_a"].id, cenario["caixa"].id]),
        {"inicio": "2024-01-01", "fim": "2024-01-31"},
    )

    corpo = response.json()
    assert len(corpo["itens"]) == 2
    assert corpo["total_debito"] == "30.00"
    assert corpo["saldo_final"] == "30.00"


def test_razao_ordena_cronologicamente_mesmo_quando_insercao_e_inversa(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    # Insere o lançamento de data POSTERIOR primeiro (ganha o id MENOR) e o
    # de data ANTERIOR depois (ganha o id MAIOR) — se o Razão ordenasse por
    # id em vez de por data, a coluna "saldo" acumularia na ordem errada.
    lancamento_tarde = criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 20),
        historico="Lançamento tardio, inserido primeiro",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("200.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("200.00")},
        ],
    )
    lancamento_cedo = criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 5),
        historico="Lançamento antecipado, inserido depois",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("50.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("50.00")},
        ],
    )
    assert lancamento_tarde.id < lancamento_cedo.id

    response = client.get(
        reverse("contabilidade:razao", args=[cenario["empresa_a"].id, cenario["caixa"].id]),
        {"inicio": "2024-01-01", "fim": "2024-01-31"},
    )

    corpo = response.json()
    assert [item["data"] for item in corpo["itens"]] == ["2024-01-05", "2024-01-20"]
    assert [item["saldo"] for item in corpo["itens"]] == ["50.00", "250.00"]


def test_diario_desempate_estavel_por_criado_em_e_id_na_mesma_data(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    lancamento_1 = criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 10),
        historico="Primeiro",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("10.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("10.00")},
        ],
    )
    lancamento_2 = criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 10),
        historico="Segundo",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("20.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("20.00")},
        ],
    )
    # Força o MESMO `criado_em` para os dois (via `.update()`, que não passa
    # por `save()`), removendo a distinção temporal natural — o desempate só
    # pode vir do `id`, ascendente. Sem isto, o mutante que remove o
    # desempate por criado_em/id ainda poderia, por acaso, ordenar certo pela
    # ordem natural de criação.
    mesmo_instante = timezone.now()
    LancamentoContabil.objects.filter(pk__in=[lancamento_1.id, lancamento_2.id]).update(
        criado_em=mesmo_instante
    )

    response = client.get(
        reverse("contabilidade:diario", args=[cenario["empresa_a"].id]),
        {"inicio": "2024-01-01", "fim": "2024-01-31"},
    )

    ids_em_ordem = [lancamento["id"] for lancamento in response.json()["lancamentos"]]
    assert ids_em_ordem == sorted([lancamento_1.id, lancamento_2.id])


# ---------------------------------------------------------------------------
# Achado 6 — ciclo/pai órfão na hierarquia: nunca 500; bloqueado na origem
# ---------------------------------------------------------------------------


def test_balancete_com_ciclo_na_hierarquia_nao_derruba_com_500(client, cenario_hierarquico):
    h = cenario_hierarquico
    _autenticar(client, h["escritorio"])
    # Ciclo Ativo -> Circulante -> Ativo (Circulante já tem conta_pai=Ativo
    # pela fixture; aqui invertemos, criando o laço). Só alcançável por ORM
    # direto (.update() não chama Conta.clean()) — mesma via da auditoria.
    Conta.objects.filter(pk=h["ativo"].id).update(conta_pai=h["circulante"].id)

    response = client.get(
        reverse("contabilidade:balancete", args=[h["empresa"].id]),
        {"inicio": "2024-01-01", "fim": "2024-01-31"},
    )

    assert response.status_code == 409
    assert h["ativo"].codigo in response.json()["detail"]


def test_balancete_conta_pai_de_si_mesma_nao_derruba_com_500(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    Conta.objects.filter(pk=cenario["caixa"].id).update(conta_pai=cenario["caixa"].id)

    response = client.get(
        reverse("contabilidade:balancete", args=[cenario["empresa_a"].id]),
        {"inicio": "2024-01-01", "fim": "2024-01-31"},
    )

    assert response.status_code == 409
    assert cenario["caixa"].codigo in response.json()["detail"]


def test_balancete_conta_pai_de_outra_empresa_nao_derruba_com_500(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    # `conta_pai` de OUTRA empresa: só alcançável por ORM direto
    # (`.objects.create()` não chama `full_clean()`, então não passa por
    # `Conta.clean()` — mesma via que a auditoria usou).
    conta_orfa = Conta.objects.create(
        empresa=cenario["empresa_a"],
        conta_pai=cenario["caixa_b"],
        codigo="9",
        nome="Conta órfã",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )

    response = client.get(
        reverse("contabilidade:balancete", args=[cenario["empresa_a"].id]),
        {"inicio": "2024-01-01", "fim": "2024-01-31"},
    )

    assert response.status_code == 409
    assert conta_orfa.codigo in response.json()["detail"]


def test_razao_de_sintetica_com_ciclo_na_hierarquia_nao_derruba_com_500(
    client, cenario_hierarquico
):
    h = cenario_hierarquico
    _autenticar(client, h["escritorio"])
    Conta.objects.filter(pk=h["ativo"].id).update(conta_pai=h["circulante"].id)

    response = client.get(
        reverse("contabilidade:razao", args=[h["empresa"].id, h["ativo"].id]),
        {"inicio": "2024-01-01", "fim": "2024-01-31"},
    )

    assert response.status_code == 409


def test_conferencia_aponta_ciclo_na_hierarquia_em_vez_de_derrubar(client, cenario_hierarquico):
    h = cenario_hierarquico
    _autenticar(client, h["escritorio"])
    Conta.objects.filter(pk=h["ativo"].id).update(conta_pai=h["circulante"].id)

    response = client.get(
        reverse("contabilidade:conferencia-lotes-desbalanceados", args=[h["empresa"].id])
    )

    assert response.status_code == 200
    inconsistencias = response.json()["hierarquia_inconsistente"]
    assert len(inconsistencias) == 1
    assert h["ativo"].codigo in inconsistencias[0]


def test_conta_clean_recusa_pai_que_e_descendente_da_propria_conta(cenario_hierarquico):
    h = cenario_hierarquico
    ativo = h["ativo"]
    ativo.conta_pai = h["caixa"]  # "Caixa" é descendente de "Ativo" (via Circulante)

    with pytest.raises(ValidationError):
        ativo.full_clean()


def test_conta_clean_recusa_conta_pai_de_si_mesma(cenario):
    caixa = cenario["caixa"]
    caixa.conta_pai = caixa

    with pytest.raises(ValidationError):
        caixa.full_clean()


# ---------------------------------------------------------------------------
# Achado 8 — Razão de conta SINTÉTICA consolida as descendentes (DE-020)
# ---------------------------------------------------------------------------


def test_razao_de_conta_sintetica_consolida_itens_das_descendentes(client, cenario_hierarquico):
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
    periodo = {"inicio": "2024-01-01", "fim": "2024-01-31"}

    razao_grupo = client.get(
        reverse("contabilidade:razao", args=[h["empresa"].id, h["ativo"].id]), periodo
    ).json()
    balancete = client.get(
        reverse("contabilidade:balancete", args=[h["empresa"].id]), periodo
    ).json()
    linha_ativo = next(linha for linha in balancete["contas"] if linha["conta"] == "1")

    assert razao_grupo["analitica"] is False
    assert razao_grupo["consolidado"] is True
    assert razao_grupo["saldo_anterior"] == linha_ativo["saldo_anterior"]
    assert razao_grupo["total_debito"] == linha_ativo["debitos"]
    assert razao_grupo["total_credito"] == linha_ativo["creditos"]
    assert razao_grupo["saldo_final"] == linha_ativo["saldo_final"]
    assert len(razao_grupo["itens"]) == 2
    assert {item["conta"] for item in razao_grupo["itens"]} == {"1.1.01", "1.1.02"}


def test_razao_de_conta_analitica_nao_e_marcado_como_consolidado(client, cenario):
    _autenticar(client, cenario["escritorio_a"])

    response = client.get(
        reverse("contabilidade:razao", args=[cenario["empresa_a"].id, cenario["caixa"].id]),
        {"inicio": "2024-01-01", "fim": "2024-01-31"},
    )

    corpo = response.json()
    assert corpo["analitica"] is True
    assert corpo["consolidado"] is False


# ---------------------------------------------------------------------------
# Achado 9 — conferência distingue lote "sem_partidas" de "desbalanceado"
# ---------------------------------------------------------------------------


def test_conferencia_distingue_lote_sem_partidas_de_lote_desbalanceado(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    lote_vazio = LancamentoContabil.objects.create(
        empresa=cenario["empresa_a"], data=date(2024, 1, 9), historico="Lote sem nenhuma partida"
    )
    lote_unico = LancamentoContabil.objects.create(
        empresa=cenario["empresa_a"], data=date(2024, 1, 9), historico="Lote com uma só partida"
    )
    ItemLancamento.objects.create(
        lancamento=lote_unico,
        conta=cenario["caixa"],
        tipo=TipoPartida.DEBITO,
        valor=Decimal("5.00"),
    )
    lote_desbalanceado = LancamentoContabil.objects.create(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 9),
        historico="Lote com duas partidas desiguais",
    )
    ItemLancamento.objects.create(
        lancamento=lote_desbalanceado,
        conta=cenario["caixa"],
        tipo=TipoPartida.DEBITO,
        valor=Decimal("10.00"),
    )
    ItemLancamento.objects.create(
        lancamento=lote_desbalanceado,
        conta=cenario["capital"],
        tipo=TipoPartida.CREDITO,
        valor=Decimal("9.00"),
    )

    response = client.get(
        reverse("contabilidade:conferencia-lotes-desbalanceados", args=[cenario["empresa_a"].id])
    )

    lotes = {lote["id"]: lote for lote in response.json()["lotes"]}
    assert lotes[lote_vazio.id]["motivo"] == "sem_partidas"
    # Achado novo 12: um lote com UMA partida é "partida_unica", não
    # "sem_partidas" — antes desta correção, os dois rótulos eram os
    # mesmos, e a linha de "lote_unico" dizia "sem_partidas" ao lado de um
    # total de 5,00, contradizendo a si mesma (a mesma falha de coerência
    # interna que o achado 3 apontou, agora na ferramenta de diagnóstico).
    assert lotes[lote_unico.id]["motivo"] == "partida_unica"
    assert lotes[lote_desbalanceado.id]["motivo"] == "desbalanceado"
    assert lotes[lote_desbalanceado.id]["diferenca"] == "1.00"


# ---------------------------------------------------------------------------
# Achado 10 — item cruzado entre empresas não vaza no Razão nem no Balancete
# ---------------------------------------------------------------------------


def test_item_de_lancamento_de_outra_empresa_nao_aparece_no_razao_nem_no_balancete(client, cenario):
    # Reprodução do achado 10: lançamento LEGÍTIMO da empresa A recebe, por
    # ORM direto, um item extra apontando para uma conta da empresa B — só
    # alcançável fora do serviço `criar_lancamento` (que valida
    # `conta.empresa_id == empresa.id`).
    _autenticar(client, cenario["escritorio_a"])
    lancamento_a = criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 5),
        historico="Lançamento de A",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("100.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("100.00")},
        ],
    )
    ItemLancamento.objects.create(
        lancamento=lancamento_a,
        conta=cenario["caixa_b"],
        tipo=TipoPartida.DEBITO,
        valor=Decimal("7.00"),
    )

    periodo = {"inicio": "2024-01-01", "fim": "2024-01-31"}

    razao_b = client.get(
        reverse("contabilidade:razao", args=[cenario["empresa_b"].id, cenario["caixa_b"].id]),
        periodo,
    )
    # `escritorio_a` não tem vínculo com a empresa B: 404, e sem o item de A.
    assert razao_b.status_code == 404

    _autenticar(client, cenario["escritorio_b"], username="gestor-b")
    razao_b_autenticado = client.get(
        reverse("contabilidade:razao", args=[cenario["empresa_b"].id, cenario["caixa_b"].id]),
        periodo,
    ).json()
    assert razao_b_autenticado["itens"] == []
    assert razao_b_autenticado["saldo_final"] == "0.00"

    balancete_b = client.get(
        reverse("contabilidade:balancete", args=[cenario["empresa_b"].id]), periodo
    ).json()
    linha_caixa_b = next(linha for linha in balancete_b["contas"] if linha["conta"] == "1.1")
    assert linha_caixa_b["debitos"] == "0.00"
    assert balancete_b["total_debitos"] == "0.00"


# ---------------------------------------------------------------------------
# Achado 11 — papel CLIENTE deixa de ler a contabilidade; demais continuam
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "papel,status_esperado",
    [
        (Papel.ADMINISTRADOR, 200),
        (Papel.GESTOR, 200),
        (Papel.ANALISTA, 200),
        (Papel.FINANCEIRO, 200),
        (Papel.PARALEGAL, 200),
        (Papel.CLIENTE, 403),
    ],
)
def test_leitura_das_quatro_rotas_de_contabilidade_depende_do_papel(
    client, cenario, papel, status_esperado
):
    # Achado novo 2 (rodada 2): estendido de QUATRO para TODAS as rotas de
    # LEITURA de contabilidade — `contas/` (plano de contas) e
    # `lancamentos/` (Diário "crú", sem período) continuavam devolvendo a
    # escrituração completa ao papel CLIENTE depois da correção original,
    # porque a permissão só tinha sido aplicada às quatro rotas CRIADAS por
    # esta etapa (Diário, Razão, Balancete, conferência), não a estas duas,
    # que já existiam antes. O nome do teste ficou histórico; o comentário
    # documenta o alcance real.
    _usuario_com_papel(papel, cenario["escritorio_a"], f"usuario-{papel.value}")
    client.login(username=f"usuario-{papel.value}", password="senha-forte-123")
    periodo = {"inicio": "2024-01-01", "fim": "2024-01-31"}

    rotas = [
        reverse("contabilidade:diario", args=[cenario["empresa_a"].id]),
        reverse("contabilidade:razao", args=[cenario["empresa_a"].id, cenario["caixa"].id]),
        reverse("contabilidade:balancete", args=[cenario["empresa_a"].id]),
        reverse("contabilidade:conferencia-lotes-desbalanceados", args=[cenario["empresa_a"].id]),
        reverse("contabilidade:contas", args=[cenario["empresa_a"].id]),
        reverse("contabilidade:lancamentos", args=[cenario["empresa_a"].id]),
    ]
    for rota in rotas:
        response = client.get(rota, periodo)
        assert response.status_code == status_esperado, rota


def test_leitura_de_lancamentos_e_contas_pelo_cliente_nao_devolve_a_escrituracao(client, cenario):
    """Achado novo 2, evidência de CONTEÚDO (não só o status): antes desta
    correção, `GET .../lancamentos/` devolvia a escrituração inteira —
    histórico, valores e partidas — ao papel CLIENTE, mesmo sem período.
    Reproduz literalmente o corpo mostrado no relatório da auditoria.
    """
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 5),
        historico="SEGREDO do cliente X: NF 123 de Fulano",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("9999.99")},
            {
                "conta": cenario["capital"],
                "tipo": TipoPartida.CREDITO,
                "valor": Decimal("9999.99"),
            },
        ],
    )
    _usuario_com_papel(Papel.CLIENTE, cenario["escritorio_a"], "cliente-sem-acesso")
    client.login(username="cliente-sem-acesso", password="senha-forte-123")

    resposta_lancamentos = client.get(
        reverse("contabilidade:lancamentos", args=[cenario["empresa_a"].id])
    )
    resposta_contas = client.get(reverse("contabilidade:contas", args=[cenario["empresa_a"].id]))

    assert resposta_lancamentos.status_code == 403
    assert "SEGREDO" not in resposta_lancamentos.content.decode()
    assert resposta_contas.status_code == 403
    assert "Caixa" not in resposta_contas.content.decode()


# ---------------------------------------------------------------------------
# Achado 12 — período e nível recusam formato fora do contrato (sem
# reinterpretar em silêncio)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("inicio", ["2026-W01-1", "20260101"])
def test_balancete_recusa_formato_de_data_fora_do_contrato_aaaa_mm_dd(client, cenario, inicio):
    _autenticar(client, cenario["escritorio_a"])

    response = client.get(
        reverse("contabilidade:balancete", args=[cenario["empresa_a"].id]),
        {"inicio": inicio, "fim": "2026-01-31"},
    )

    assert response.status_code == 400


@pytest.mark.parametrize("nivel", ["1_0", " 2 ", "+2"])
def test_balancete_recusa_nivel_fora_do_formato_numerico_simples(client, cenario, nivel):
    _autenticar(client, cenario["escritorio_a"])

    response = client.get(
        reverse("contabilidade:balancete", args=[cenario["empresa_a"].id]),
        {"inicio": "2026-01-01", "fim": "2026-01-31", "nivel": nivel},
    )

    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Achado novo 11 — `nivel` e data recusam dígito Unicode; `nivel` tem teto
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "inicio",
    [
        "٢٠٢٦-٠١-٠١",  # dígitos arábico-índicos — \d os aceitava, [0-9] não
        "２０２６-０１-０１",  # dígitos largos (fullwidth)
    ],
)
def test_balancete_recusa_data_com_digito_unicode_nao_ascii(client, cenario, inicio):
    _autenticar(client, cenario["escritorio_a"])

    response = client.get(
        reverse("contabilidade:balancete", args=[cenario["empresa_a"].id]),
        {"inicio": inicio, "fim": "2026-01-31"},
    )

    assert response.status_code == 400


def test_padrao_data_simples_recusa_digito_nao_ascii_na_propria_regex():
    """A regex `_PADRAO_DATA_SIMPLES`, testada DIRETAMENTE — não pelo
    comportamento da rota. O relatório da auditoria registrou que, para
    data, o buraco na regex era "fechado por acidente" por
    `date.fromisoformat` (que já recusa dígito não-ASCII por conta própria);
    ou seja, o teste comportamental acima NÃO discrimina `\\d` de `[0-9]` —
    os dois dão 400, um pela regex, outro pelo fromisoformat. Esta checagem
    prova a regex em si, independente desse acidente.
    """
    from apps.contabilidade.views import _PADRAO_DATA_SIMPLES

    assert _PADRAO_DATA_SIMPLES.fullmatch("2026-01-01")
    assert not _PADRAO_DATA_SIMPLES.fullmatch("٢٠٢٦-٠١-٠١")
    assert not _PADRAO_DATA_SIMPLES.fullmatch("２０２６-０１-０１")


@pytest.mark.parametrize(
    "nivel",
    [
        "٢",  # dígito arábico-índico para "2" — antes era aceito como nível 2
        "２",  # dígito largo (fullwidth) para "2"
        "999999999999999999999999999999",  # inteiro Python válido, sem teto
    ],
)
def test_balancete_recusa_nivel_com_digito_unicode_ou_acima_do_teto(client, cenario, nivel):
    _autenticar(client, cenario["escritorio_a"])

    response = client.get(
        reverse("contabilidade:balancete", args=[cenario["empresa_a"].id]),
        {"inicio": "2026-01-01", "fim": "2026-01-31", "nivel": nivel},
    )

    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Observação menor 4 — mensagem de erro do critério 2, não só o status
# ---------------------------------------------------------------------------


def test_balancete_periodo_ausente_devolve_mensagem_util_nao_so_o_status(client, cenario):
    _autenticar(client, cenario["escritorio_a"])

    response = client.get(reverse("contabilidade:balancete", args=[cenario["empresa_a"].id]), {})

    assert response.status_code == 400
    # `DRFValidationError` com uma string simples serializa como uma LISTA
    # de um item (comportamento do DRF), não como {"detail": ...} — só as
    # respostas 409 construídas manualmente nesta etapa (HierarquiaInconsistente,
    # ChaveIdempotenciaConflitante) usam o formato {"detail": ...}.
    detalhe = response.json()[0]
    assert "inicio" in detalhe
    assert "AAAA-MM-DD" in detalhe


def test_balancete_periodo_invertido_devolve_mensagem_com_as_duas_datas(client, cenario):
    _autenticar(client, cenario["escritorio_a"])

    response = client.get(
        reverse("contabilidade:balancete", args=[cenario["empresa_a"].id]),
        {"inicio": "2024-01-31", "fim": "2024-01-01"},
    )

    assert response.status_code == 400
    detalhe = response.json()[0]
    assert "2024-01-31" in detalhe
    assert "2024-01-01" in detalhe


# ---------------------------------------------------------------------------
# Achado 14 — teto explícito de consultas (mantendo a comparação 3 x 30)
# ---------------------------------------------------------------------------


def test_balancete_numero_de_consultas_tem_teto_explicito(
    client, cenario, django_assert_max_num_queries
):
    _autenticar(client, cenario["escritorio_a"])
    empresa = cenario["empresa_a"]
    periodo = {"inicio": "2024-01-01", "fim": "2024-01-31"}
    # Aquecimento: paga as consultas de sessão/permissão que não se repetem.
    client.get(reverse("contabilidade:balancete", args=[empresa.id]), periodo)

    # Teto medido com margem: hoje a rota faz poucas consultas de tamanho
    # constante (contas, agregado por conta, agregado do total, sessão e
    # permissão). Fixar um valor evita que uma "otimização" futura
    # reintroduza N+1 sem que teste algum acuse — era exatamente o que o
    # achado 14 apontou como faltante (a comparação 3x30, por si só, também
    # passaria com 50 consultas constantes).
    with django_assert_max_num_queries(10):
        resposta = client.get(reverse("contabilidade:balancete", args=[empresa.id]), periodo)
    assert resposta.status_code == 200


def test_diario_numero_de_consultas_nao_cresce_e_tem_teto_explicito(
    client, cenario, django_assert_max_num_queries
):
    _autenticar(client, cenario["escritorio_a"])
    empresa = cenario["empresa_a"]
    periodo = {"inicio": "2024-01-01", "fim": "2024-01-31"}
    client.get(reverse("contabilidade:diario", args=[empresa.id]), periodo)  # aquecimento

    def _criar_lancamentos(quantidade):
        for i in range(quantidade):
            criar_lancamento(
                empresa=empresa,
                data=date(2024, 1, 15),
                historico=f"Movimento de teste {i}",
                itens=[
                    {
                        "conta": cenario["caixa"],
                        "tipo": TipoPartida.DEBITO,
                        "valor": Decimal("10.00"),
                    },
                    {
                        "conta": cenario["capital"],
                        "tipo": TipoPartida.CREDITO,
                        "valor": Decimal("10.00"),
                    },
                ],
            )

    _criar_lancamentos(3)
    with CaptureQueriesContext(connection) as poucos:
        resposta_pequena = client.get(reverse("contabilidade:diario", args=[empresa.id]), periodo)
    assert resposta_pequena.status_code == 200

    _criar_lancamentos(27)  # total: 30 lançamentos
    with CaptureQueriesContext(connection) as muitos:
        resposta_grande = client.get(reverse("contabilidade:diario", args=[empresa.id]), periodo)
    assert resposta_grande.status_code == 200
    assert len(resposta_grande.json()["lancamentos"]) > len(resposta_pequena.json()["lancamentos"])

    assert len(muitos) == len(poucos)

    with django_assert_max_num_queries(10):
        client.get(reverse("contabilidade:diario", args=[empresa.id]), periodo)


# ===========================================================================
# Achados novos da auditoria da DL-015, rodada 2
# (docs/auditorias/2026-09-14-dl-015-rodada-2.md). Reprovada.
# ===========================================================================


# ---------------------------------------------------------------------------
# Achado novo 1 — DE-022: "analítica" = folha da árvore. Razão e Balancete
# concordam sobre quando consolidar, mesmo quando a conta ACEITA lançamento
# e TEM filhas (estado que a API cria pelo valor padrão de
# `aceita_lancamento`, sem exigir nada inconsistente — DE-022 explica por
# que este estado NÃO é proibido).
# ---------------------------------------------------------------------------


def test_de022_conta_que_aceita_lancamento_e_tem_filha_bate_razao_e_balancete(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    periodo = {"inicio": "2024-01-01", "fim": "2024-01-31"}

    # Reprodução do achado novo 1, 100% pela API: pai e filha criados SEM
    # desmarcar `aceita_lancamento` (o valor padrão do modelo é `True`).
    resposta_pai = client.post(
        reverse("contabilidade:contas", args=[cenario["empresa_a"].id]),
        data={
            "codigo": "4",
            "nome": "Despesas operacionais",
            "tipo": TipoConta.DESPESA,
            "natureza": NaturezaConta.DEVEDORA,
        },
        content_type="application/json",
    )
    assert resposta_pai.status_code == 201
    assert resposta_pai.json()["aceita_lancamento"] is True
    pai_id = resposta_pai.json()["id"]

    resposta_filha = client.post(
        reverse("contabilidade:contas", args=[cenario["empresa_a"].id]),
        data={
            "codigo": "4.1",
            "nome": "Aluguel",
            "tipo": TipoConta.DESPESA,
            "natureza": NaturezaConta.DEVEDORA,
            "conta_pai": pai_id,
        },
        content_type="application/json",
    )
    assert resposta_filha.status_code == 201
    filha = Conta.objects.get(pk=resposta_filha.json()["id"])

    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 5),
        historico="Aluguel de janeiro",
        itens=[
            {"conta": filha, "tipo": TipoPartida.DEBITO, "valor": Decimal("1500.00")},
            {
                "conta": cenario["capital"],
                "tipo": TipoPartida.CREDITO,
                "valor": Decimal("1500.00"),
            },
        ],
    )

    balancete = client.get(
        reverse("contabilidade:balancete", args=[cenario["empresa_a"].id]), periodo
    ).json()
    razao_pai = client.get(
        reverse("contabilidade:razao", args=[cenario["empresa_a"].id, pai_id]), periodo
    ).json()

    linha_pai = next(linha for linha in balancete["contas"] if linha["conta"] == "4")
    # "4" tem descendente ("4.1") -> não é folha -> não é "analitica" (DE-022).
    assert linha_pai["analitica"] is False
    assert linha_pai["debitos"] == "1500.00"
    assert linha_pai["saldo_final"] == "1500.00"

    # (i) Razão(pai) bate com a linha do Balancete(pai) nos QUATRO valores —
    # a prova central do achado (mesma conta, mesmo período, mesma história).
    assert razao_pai["consolidado"] is True
    assert razao_pai["analitica"] is False
    assert razao_pai["saldo_anterior"] == linha_pai["saldo_anterior"]
    assert razao_pai["total_debito"] == linha_pai["debitos"]
    assert razao_pai["total_credito"] == linha_pai["creditos"]
    assert razao_pai["saldo_final"] == linha_pai["saldo_final"]

    # (ii) a soma das linhas marcadas como "analitica" (folha, DE-022)
    # reconcilia com o total_debitos — COM e SEM `nivel`. Antes da correção,
    # "4" e "4.1" seriam AS DUAS marcadas `analitica: true` (o critério era
    # `aceita_lancamento`, e nenhuma delas foi desmarcada), e a soma daria
    # 3000,00 contra um rodapé de 1500,00.
    soma_folhas = sum(
        Decimal(linha["debitos"]) for linha in balancete["contas"] if linha["analitica"]
    )
    assert soma_folhas == Decimal(balancete["total_debitos"]) == Decimal("1500.00")

    balancete_com_nivel = client.get(
        reverse("contabilidade:balancete", args=[cenario["empresa_a"].id]),
        {**periodo, "nivel": "2"},
    ).json()
    soma_folhas_com_nivel = sum(
        Decimal(linha["debitos"]) for linha in balancete_com_nivel["contas"] if linha["analitica"]
    )
    assert (
        soma_folhas_com_nivel == Decimal(balancete_com_nivel["total_debitos"]) == Decimal("1500.00")
    )

    # (iii) a conferência aponta "4" na quarta categoria (DE-022) — não como
    # erro, só como um caso que o contador pode querer olhar.
    conferencia = client.get(
        reverse("contabilidade:conferencia-lotes-desbalanceados", args=[cenario["empresa_a"].id])
    ).json()
    codigos_apontados = {
        item["conta"] for item in conferencia["contas_que_aceitam_lancamento_e_tem_subordinadas"]
    }
    assert "4" in codigos_apontados
    assert "4.1" not in codigos_apontados  # "4.1" não tem subordinada — não entra


def test_de022_movimento_proprio_no_pai_e_na_filha_nao_perde_nem_dobra(client, cenario):
    """Segunda reprodução do achado novo 1 (rodada 2): movimento PRÓPRIO no
    pai (60,00) E na filha (40,00) — o relatório mediu Razão do pai em 60,00
    (ou 0,00) contra Balancete em 100,00 (ou 1500,00), e soma das linhas
    analíticas em 1140,00 contra rodapé de 1100,00.

    Também é o cenário do achado novo 3 da rodada 3 / DE-024 §2: a soma das
    linhas "analitica" (folha) não reconciliava com o rodapé quando o pai
    tinha movimento próprio E filha (a folha "5.1" sozinha soma 40,00,
    contra um rodapé de 100,00 — os 60,00 do pai não apareciam em NENHUMA
    folha). A correção acrescenta `debitos_proprios`/`creditos_proprios` a
    CADA linha (o que foi lançado DIRETO nela, sem o das descendentes); a
    invariante que agora vale, testada COM e SEM `nivel`, é: a soma dos
    PRÓPRIOS de TODAS as linhas exibidas é sempre `total_debitos`/
    `total_creditos` — nunca depende de quais linhas são folha.
    """
    _autenticar(client, cenario["escritorio_a"])
    periodo = {"inicio": "2024-01-01", "fim": "2024-01-31"}
    pai = Conta.objects.create(
        empresa=cenario["empresa_a"],
        codigo="5",
        nome="Resultado",
        tipo=TipoConta.DESPESA,
        natureza=NaturezaConta.DEVEDORA,
        # aceita_lancamento NÃO foi desmarcado — fica no padrão True.
    )
    filha = Conta.objects.create(
        empresa=cenario["empresa_a"],
        codigo="5.1",
        nome="Resultado detalhe",
        tipo=TipoConta.DESPESA,
        natureza=NaturezaConta.DEVEDORA,
        conta_pai=pai,
    )
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 5),
        historico="Movimento do pai",
        itens=[
            {"conta": pai, "tipo": TipoPartida.DEBITO, "valor": Decimal("60.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("60.00")},
        ],
    )
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 10),
        historico="Movimento da filha",
        itens=[
            {"conta": filha, "tipo": TipoPartida.DEBITO, "valor": Decimal("40.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("40.00")},
        ],
    )

    balancete = client.get(
        reverse("contabilidade:balancete", args=[cenario["empresa_a"].id]), periodo
    ).json()
    razao_pai = client.get(
        reverse("contabilidade:razao", args=[cenario["empresa_a"].id, pai.id]), periodo
    ).json()
    linha_pai = next(linha for linha in balancete["contas"] if linha["conta"] == "5")

    assert linha_pai["debitos"] == "100.00"  # 60 (próprio) + 40 (filha)
    assert razao_pai["total_debito"] == linha_pai["debitos"] == "100.00"
    assert razao_pai["saldo_final"] == linha_pai["saldo_final"]

    soma_folhas = sum(
        Decimal(linha["debitos"])
        for linha in balancete["contas"]
        if linha["analitica"] and linha["conta"] in {"5", "5.1"}
    )
    assert soma_folhas == Decimal("40.00")  # só "5.1" é folha; "5" tem descendente

    # Achado novo 3 / DE-024 §2: "5" (pai) declara o PRÓPRIO (60,00) — o que
    # a soma das folhas, acima, nunca conseguiria mostrar — e "5.1" (filha)
    # continua com o próprio igual ao consolidado, porque é folha.
    linha_filha = next(linha for linha in balancete["contas"] if linha["conta"] == "5.1")
    assert linha_pai["debitos_proprios"] == "60.00"
    assert linha_filha["debitos_proprios"] == "40.00"

    def _soma_dos_proprios_reconcilia(corpo_balancete):
        soma_debitos_proprios = sum(
            Decimal(linha["debitos_proprios"]) for linha in corpo_balancete["contas"]
        )
        soma_creditos_proprios = sum(
            Decimal(linha["creditos_proprios"]) for linha in corpo_balancete["contas"]
        )
        total_debitos = Decimal(corpo_balancete["total_debitos"])
        total_creditos = Decimal(corpo_balancete["total_creditos"])
        assert soma_debitos_proprios == total_debitos == Decimal("100.00")
        assert soma_creditos_proprios == total_creditos == Decimal("100.00")

    # SEM `nivel`: "5", "5.1" e "2.1" (capital, credor dos dois lançamentos)
    # aparecem, cada uma com seu próprio — nenhuma soma valor da outra.
    _soma_dos_proprios_reconcilia(balancete)

    # COM `nivel=1`: "5.1" fica DE FORA da lista (nível 2 > 1) — o próprio
    # dela (40,00) tem que ser ABSORVIDO pela linha de "5" (nível 1, o
    # ancestral visível mais profundo), ou a soma cairia para 60,00 contra
    # um rodapé que continua 100,00 (o rodapé NUNCA depende de `nivel`).
    balancete_nivel_1 = client.get(
        reverse("contabilidade:balancete", args=[cenario["empresa_a"].id]),
        {**periodo, "nivel": "1"},
    ).json()
    assert {linha["conta"] for linha in balancete_nivel_1["contas"]} == {"1.1", "2.1", "5"}
    linha_pai_nivel_1 = next(
        linha for linha in balancete_nivel_1["contas"] if linha["conta"] == "5"
    )
    assert linha_pai_nivel_1["debitos_proprios"] == "100.00"  # absorveu o de "5.1"
    _soma_dos_proprios_reconcilia(balancete_nivel_1)

    # COM `nivel=2`: "5.1" volta a aparecer, e o próprio de "5" volta a ser
    # só o dele mesmo (60,00) — mesmo resultado do balancete sem filtro.
    balancete_nivel_2 = client.get(
        reverse("contabilidade:balancete", args=[cenario["empresa_a"].id]),
        {**periodo, "nivel": "2"},
    ).json()
    linha_pai_nivel_2 = next(
        linha for linha in balancete_nivel_2["contas"] if linha["conta"] == "5"
    )
    assert linha_pai_nivel_2["debitos_proprios"] == "60.00"
    _soma_dos_proprios_reconcilia(balancete_nivel_2)


# ---------------------------------------------------------------------------
# Achado novo 3 — caso de referência do Fred (mapa-funcional-contabil.md,
# seção "Conta retificadora, apresentação de saldo e implantação") e
# achado novo 9 — sinal do Razão consolidado em grupo com retificadora
# ---------------------------------------------------------------------------


@pytest.fixture
def cenario_imobilizado_fred(cenario):
    """Grupo "Imobilizado" com duas contas de bens e uma retificadora, e o
    lançamento ÚNICO de implantação de saldos que o Fred enviou — números
    literais de docs/projeto/mapa-funcional-contabil.md, seção "Conta
    retificadora, apresentação de saldo e implantação":

        1.2.3.03.001 Máquinas e equipamentos ......... 1.437,50 D
        1.2.3.04.001 Veículos ......................... 29.900,00 D
        1.2.3.07.003 (-) Depreciações de máq. e equip. .. 2.074,18 C
        1.2.3        Imobilizado (grupo) ............... 29.263,32 D

    O lançamento de implantação (mapa: "um único lançamento, do tipo vários
    débitos para vários créditos, datado na data de encerramento do balanço
    anterior — tipicamente 31/12") precisa fechar (débito = crédito) na
    TOTALIDADE, não dentro do grupo — por isso o lado credor que falta
    (29.263,32) entra em "Capital Social", representando o resto do balanço
    que também compõe a implantação.
    """
    imobilizado = Conta.objects.create(
        empresa=cenario["empresa_a"],
        codigo="1.2.3",
        nome="Imobilizado",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    maquinas = Conta.objects.create(
        empresa=cenario["empresa_a"],
        codigo="1.2.3.03.001",
        nome="Máquinas e equipamentos",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        conta_pai=imobilizado,
    )
    veiculos = Conta.objects.create(
        empresa=cenario["empresa_a"],
        codigo="1.2.3.04.001",
        nome="Veículos",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        conta_pai=imobilizado,
    )
    depreciacao = Conta.objects.create(
        empresa=cenario["empresa_a"],
        codigo="1.2.3.07.003",
        nome="(-) Depreciações de máquinas e equipamentos",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.CREDORA,  # retificadora: natureza OPOSTA ao grupo
        conta_pai=imobilizado,
    )
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2023, 12, 31),  # encerramento do balanço anterior
        historico="Implantação de saldos - balanço de 31/12/2023",
        itens=[
            {"conta": maquinas, "tipo": TipoPartida.DEBITO, "valor": Decimal("1437.50")},
            {"conta": veiculos, "tipo": TipoPartida.DEBITO, "valor": Decimal("29900.00")},
            {"conta": depreciacao, "tipo": TipoPartida.CREDITO, "valor": Decimal("2074.18")},
            {
                "conta": cenario["capital"],
                "tipo": TipoPartida.CREDITO,
                "valor": Decimal("29263.32"),
            },
        ],
    )
    return {
        **cenario,
        "imobilizado": imobilizado,
        "maquinas": maquinas,
        "veiculos": veiculos,
        "depreciacao": depreciacao,
    }


def test_caso_referencia_fred_grupo_imobilizado_fecha_em_29263_32(client, cenario_imobilizado_fred):
    c = cenario_imobilizado_fred
    _autenticar(client, c["escritorio_a"])
    periodo = {"inicio": "2023-01-01", "fim": "2023-12-31"}

    balancete = client.get(
        reverse("contabilidade:balancete", args=[c["empresa_a"].id]), periodo
    ).json()
    linhas = {linha["conta"]: linha for linha in balancete["contas"]}

    assert linhas["1.2.3.03.001"]["debitos"] == "1437.50"
    assert linhas["1.2.3.03.001"]["saldo_final"] == "1437.50"
    assert linhas["1.2.3.04.001"]["debitos"] == "29900.00"
    assert linhas["1.2.3.04.001"]["saldo_final"] == "29900.00"
    assert linhas["1.2.3.07.003"]["creditos"] == "2074.18"
    assert linhas["1.2.3.07.003"]["saldo_final"] == "2074.18"

    grupo = linhas["1.2.3"]
    assert grupo["debitos"] == "31337.50"
    assert grupo["creditos"] == "2074.18"
    assert grupo["saldo_final"] == "29263.32"  # o número do balanço do Fred


def test_razao_consolidado_de_grupo_com_retificadora_aplica_natureza_do_grupo(
    client, cenario_imobilizado_fred
):
    """Achado novo 9: o Razão consolidado do MESMO grupo (mesmo cenário do
    caso de referência do Fred) tem que aplicar a natureza do GRUPO, não a
    de cada descendente — inclusive na coluna "saldo" linha a linha.
    """
    c = cenario_imobilizado_fred
    _autenticar(client, c["escritorio_a"])
    periodo = {"inicio": "2023-01-01", "fim": "2023-12-31"}

    razao_grupo = client.get(
        reverse("contabilidade:razao", args=[c["empresa_a"].id, c["imobilizado"].id]), periodo
    ).json()

    assert razao_grupo["consolidado"] is True
    assert razao_grupo["analitica"] is False
    assert razao_grupo["total_debito"] == "31337.50"
    assert razao_grupo["total_credito"] == "2074.18"
    assert razao_grupo["saldo_final"] == "29263.32"

    # Coluna "saldo" linha a linha: os itens vêm em ordem cronológica; como
    # os três compartilham lançamento e criado_em, o desempate é por id, na
    # ordem em que foram criados (máquinas, veículos, depreciação).
    saldos = [item["saldo"] for item in razao_grupo["itens"]]
    assert saldos == ["1437.50", "31337.50", "29263.32"]


# ---------------------------------------------------------------------------
# Achado novo 4 — rodapé do Balancete não pode somar movimento ANTERIOR ao
# período (limite inferior da agregação do TOTAL, sem teste até agora)
# ---------------------------------------------------------------------------


def test_balancete_rodape_nao_soma_movimento_anterior_ao_periodo(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2023, 12, 1),  # ANTES do período consultado
        historico="Movimento anterior ao período",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("800.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("800.00")},
        ],
    )

    response = client.get(
        reverse("contabilidade:balancete", args=[cenario["empresa_a"].id]),
        {"inicio": "2024-01-01", "fim": "2024-01-31"},
    )

    corpo = response.json()
    # Sem NENHUM movimento dentro do período, o rodapé tem que ser ZERO —
    # não o valor do movimento anterior. O mutante N05 (remover
    # `lancamento__data__gte=inicio` da agregação do total) faz o rodapé
    # somar o movimento anterior mesmo assim, e ainda assim "fechar"
    # (débito = crédito), sem nada acusar.
    assert corpo["total_debitos"] == corpo["total_creditos"] == "0.00"
    linha_caixa = next(linha for linha in corpo["contas"] if linha["conta"] == "1.1")
    assert linha_caixa["saldo_anterior"] == "800.00"
    assert linha_caixa["debitos"] == "0.00"


def test_balancete_rodape_traz_so_o_movimento_de_dentro_do_periodo(client, cenario):
    """Segundo caso do achado novo 4: movimento ANTES, DENTRO e DEPOIS do
    período — o rodapé só pode trazer o de DENTRO.
    """
    _autenticar(client, cenario["escritorio_a"])
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2023, 12, 1),
        historico="Antes",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("800.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("800.00")},
        ],
    )
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 15),
        historico="Dentro",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("50.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("50.00")},
        ],
    )
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 2, 10),
        historico="Depois",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("30.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("30.00")},
        ],
    )

    response = client.get(
        reverse("contabilidade:balancete", args=[cenario["empresa_a"].id]),
        {"inicio": "2024-01-01", "fim": "2024-01-31"},
    )

    corpo = response.json()
    assert corpo["total_debitos"] == corpo["total_creditos"] == "50.00"


# ---------------------------------------------------------------------------
# Achado novo 5 — Razão: `saldo_anterior` também precisa filtrar por
# `lancamento__empresa` (a correção anterior só cobriu o PERÍODO)
# ---------------------------------------------------------------------------


def test_razao_saldo_anterior_nao_soma_item_de_lancamento_de_outra_empresa(client, cenario):
    # Mesma corrupção do achado 10 (item de A apontando para conta de B),
    # mas datada ANTES do período consultado — caminho do `saldo_anterior`,
    # que o teste original do achado 10 não exercitava (ele cria o item
    # cruzado DENTRO do período).
    lancamento_a = criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2023, 12, 1),  # antes do período que será consultado em B
        historico="Lançamento de A",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("100.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("100.00")},
        ],
    )
    ItemLancamento.objects.create(
        lancamento=lancamento_a,
        conta=cenario["caixa_b"],
        tipo=TipoPartida.DEBITO,
        valor=Decimal("7.00"),
    )

    _autenticar(client, cenario["escritorio_b"], username="gestor-b")
    razao_b = client.get(
        reverse("contabilidade:razao", args=[cenario["empresa_b"].id, cenario["caixa_b"].id]),
        {"inicio": "2024-01-01", "fim": "2024-01-31"},
    ).json()

    # O mutante N08 (remover `lancamento__empresa` do agregado do saldo
    # anterior) faria os 7,00 do item corrompido entrarem aqui.
    assert razao_b["saldo_anterior"] == "0.00"
    assert razao_b["saldo_final"] == "0.00"


# ---------------------------------------------------------------------------
# Achado novo 6 — ItemLancamento.clean() exige mesma empresa; admin não
# oferece inclusão de lançamento (BL-79)
# ---------------------------------------------------------------------------


def test_item_lancamento_clean_recusa_conta_de_outra_empresa(cenario):
    lancamento = LancamentoContabil.objects.create(
        empresa=cenario["empresa_a"], data=date(2024, 1, 5), historico="Lançamento"
    )
    item = ItemLancamento(
        lancamento=lancamento,
        conta=cenario["caixa_b"],  # conta da empresa B
        tipo=TipoPartida.DEBITO,
        valor=Decimal("100.00"),
    )

    with pytest.raises(ValidationError):
        item.full_clean()


def test_item_lancamento_clean_aceita_conta_da_mesma_empresa(cenario):
    lancamento = LancamentoContabil.objects.create(
        empresa=cenario["empresa_a"], data=date(2024, 1, 5), historico="Lançamento"
    )
    item = ItemLancamento(
        lancamento=lancamento,
        conta=cenario["caixa"],  # conta da empresa A, mesma do lançamento
        tipo=TipoPartida.DEBITO,
        valor=Decimal("100.00"),
    )

    item.full_clean(exclude=["id"])  # não deve levantar


@pytest.mark.parametrize(
    "itens",
    [
        # (a) item de conta de OUTRA empresa
        [("caixa", "debito", "100.00"), ("caixa_b", "debito", "7.00")],
        # (b) lote desbalanceado
        [("caixa", "debito", "100.00"), ("capital", "credito", "90.00")],
        # (c) lote sem nenhuma partida
        [],
    ],
)
def test_admin_recusa_inclusao_de_lancamento_nos_tres_casos_do_relatorio(
    client, cenario, itens, django_user_model
):
    """Achado novo 6: os três casos que a auditoria gravou pela tela de
    inclusão do admin (`admin:contabilidade_lancamentocontabil_add`) agora
    são recusados — porque a inclusão está DESABILITADA
    (`has_add_permission=False`), não porque o formulário validou cada
    caso. Os três têm que dar 403 e nada pode ser gravado.
    """
    django_user_model.objects.create_superuser(
        username="admin-teste", email="admin@escritorio.com.br", password="senha-forte-123"
    )
    client.login(username="admin-teste", password="senha-forte-123")
    total_lancamentos_antes = LancamentoContabil.objects.count()
    total_itens_antes = ItemLancamento.objects.count()

    dados = {
        "empresa": cenario["empresa_a"].id,
        "data": "2024-01-09",
        "historico": "Tentativa via admin",
        "itens-TOTAL_FORMS": str(len(itens)),
        "itens-INITIAL_FORMS": "0",
        "itens-MIN_NUM_FORMS": "0",
        "itens-MAX_NUM_FORMS": "1000",
    }
    for i, (conta_chave, tipo, valor) in enumerate(itens):
        dados[f"itens-{i}-conta"] = str(cenario[conta_chave].id)
        dados[f"itens-{i}-tipo"] = tipo
        dados[f"itens-{i}-valor"] = valor

    response = client.post(
        "/admin/contabilidade/lancamentocontabil/add/",
        data=dados,
    )

    assert response.status_code == 403
    assert LancamentoContabil.objects.count() == total_lancamentos_antes
    assert ItemLancamento.objects.count() == total_itens_antes


def test_admin_lancamento_e_somente_consulta_contrato_direto(rf, django_user_model):
    """Achado novo 1 (bloqueador) da rodada 3 / DE-024 §1: o teste ANTERIOR
    fazia `client.get("/admin/contabilidade/lancamentocontabil/")`, que
    RENDERIZA a listagem do admin — sob `CompressedManifestStaticFilesStorage`
    (config/settings.py), qualquer template com `{% static %}` (o próprio
    template do admin) exige o manifesto que só existe DEPOIS de
    `collectstatic`. A integração contínua roda `collectstatic` DEPOIS do
    `pytest`, DE PROPÓSITO (DE-012): se a ordem fosse invertida, a CI passaria
    escondendo exatamente o defeito que esse teste queria pegar. Em checkout
    limpo (`git archive` + `tar`, sem `collectstatic` nenhum antes — o que a
    CI faz), esse teste estourava `ValueError: Missing staticfiles manifest
    entry for 'admin/css/base.css'`. Os 391 "aprovados" do commit anterior só
    existiam porque a árvore de trabalho já tinha um `staticfiles/`
    (gitignored) de uma execução anterior.

    Verificamos o CONTRATO diretamente (opção (a) da correção, DE-024 §1) —
    nenhuma página é renderizada: `has_add_permission` e
    `has_delete_permission` (achado novo 2, abaixo) são falsos.
    """
    usuario = django_user_model.objects.create_superuser(
        username="admin-teste2", email="admin2@escritorio.com.br", password="senha-forte-123"
    )
    request = rf.get("/admin/contabilidade/lancamentocontabil/")
    request.user = usuario

    admin_instance = admin.site._registry[LancamentoContabil]

    assert admin_instance.has_add_permission(request) is False
    assert admin_instance.has_delete_permission(request) is False


# ---------------------------------------------------------------------------
# Achado novo 2 — o admin apaga escrituração em lote, sem rastro,
# contornando a imutabilidade (LancamentoContabil.delete() não é chamado por
# QuerySet.delete(), que é o que a ação "delete_selected" da listagem usa)
# ---------------------------------------------------------------------------


def test_admin_lancamento_nao_oferece_acao_de_exclusao_em_lote(rf, cenario, django_user_model):
    """A ação "delete_selected" da listagem chama `QuerySet.delete()`, que
    NÃO passa por `LancamentoContabil.delete()` (a guarda que levanta
    `LancamentoImutavelError`) — antes desta correção, apagava lançamento e
    itens em lote, DEFINITIVAMENTE, sem estorno, sem versão anterior e sem
    registro em `apps/auditoria`.

    Verificamos o MECANISMO diretamente, sem passar pelo `Client` — a mesma
    restrição do achado novo 1: uma requisição de ação via `Client` que a
    permissão recusa cai de volta no render NORMAL da listagem (o Django,
    com a ação fora da lista de permitidas, simplesmente ignora o POST e
    devolve a página de novo, 200) — o que reintroduziria o mesmo problema
    de renderização em checkout limpo. Testamos o que realmente importa: (1)
    "delete_selected" nunca aparece entre as ações disponíveis
    (`get_actions`), porque `has_delete_permission` é falso; (2) mesmo
    chamando `response_action` diretamente com essa ação, nada é executado
    (devolve `None`) e a contagem não muda. Mutar `has_delete_permission`
    para `True` faz a ação aparecer em `get_actions` e este teste falha.
    """
    lancamento = LancamentoContabil.objects.create(
        empresa=cenario["empresa_a"], data=date(2024, 1, 5), historico="Lançamento"
    )
    ItemLancamento.objects.create(
        lancamento=lancamento,
        conta=cenario["caixa"],
        tipo=TipoPartida.DEBITO,
        valor=Decimal("10.00"),
    )
    total_lancamentos_antes = LancamentoContabil.objects.count()
    total_itens_antes = ItemLancamento.objects.count()

    usuario = django_user_model.objects.create_superuser(
        username="admin-teste4", email="admin4@escritorio.com.br", password="senha-forte-123"
    )
    admin_instance = admin.site._registry[LancamentoContabil]
    request = rf.post(
        "/admin/contabilidade/lancamentocontabil/",
        data={
            "action": "delete_selected",
            "_selected_action": [str(lancamento.id)],
            "index": "0",
        },
    )
    request.user = usuario
    request.session = SessionStore()
    request.session.save()
    request._messages = FallbackStorage(request)

    assert "delete_selected" not in admin_instance.get_actions(request)

    resposta = admin_instance.response_action(
        request, queryset=LancamentoContabil.objects.filter(pk=lancamento.pk)
    )

    assert resposta is None  # ação não reconhecida entre as permitidas: nada executado
    assert LancamentoContabil.objects.count() == total_lancamentos_antes
    assert ItemLancamento.objects.count() == total_itens_antes


def test_admin_recusa_exclusao_individual_de_lancamento(client, cenario, django_user_model):
    """Caminho individual (botão "Excluir" na ficha, `.../<id>/delete/`):
    ANTES desta correção, a guarda de imutabilidade RODAVA (o `delete()` do
    modelo), mas como uma excepión que vazava — 500, não uma recusa
    apresentável. `has_delete_permission=False` faz o Django recusar ANTES
    de chegar no modelo: 403, e nada é tocado. Diferente do caso em lote
    acima, este caminho NÃO cai de volta em nenhum render (`delete_view`
    verifica a permissão e levanta `PermissionDenied` antes de montar
    qualquer página) — seguro usar o `Client` normalmente.
    """
    django_user_model.objects.create_superuser(
        username="admin-teste5", email="admin5@escritorio.com.br", password="senha-forte-123"
    )
    client.login(username="admin-teste5", password="senha-forte-123")
    lancamento = LancamentoContabil.objects.create(
        empresa=cenario["empresa_a"], data=date(2024, 1, 5), historico="Lançamento"
    )
    total_antes = LancamentoContabil.objects.count()

    response = client.post(
        f"/admin/contabilidade/lancamentocontabil/{lancamento.id}/delete/",
        data={"post": "yes"},
    )

    assert response.status_code == 403
    assert LancamentoContabil.objects.count() == total_antes


# ---------------------------------------------------------------------------
# Achado novo 6 — defesas sem teste que as torne observáveis: M11
# (`has_change_permission` do admin de lançamento) e M05 (`_descendentes_de`
# sem o filtro `empresa=empresa`, mais abaixo, junto do Razão)
# ---------------------------------------------------------------------------


def test_admin_recusa_alteracao_de_lancamento_por_post(client, cenario, django_user_model):
    """M11 (achado novo 6): `has_change_permission` é falso, mas nenhum
    teste fixava isso — mutar para `True` fazia a suíte inteira passar do
    mesmo jeito. `changeform_view` verifica a permissão ANTES de montar a
    página de resposta a um `POST` de salvamento (diferente do `GET`, que
    devolve a ficha em modo leitura e por isso não testamos aqui, pela
    mesma restrição do achado novo 1) — seguro usar o `Client`.
    """
    django_user_model.objects.create_superuser(
        username="admin-teste6", email="admin6@escritorio.com.br", password="senha-forte-123"
    )
    client.login(username="admin-teste6", password="senha-forte-123")
    lancamento = LancamentoContabil.objects.create(
        empresa=cenario["empresa_a"], data=date(2024, 1, 5), historico="Histórico original"
    )

    response = client.post(
        f"/admin/contabilidade/lancamentocontabil/{lancamento.id}/change/",
        data={
            "empresa": str(cenario["empresa_a"].id),
            "data": "2024-02-02",
            "historico": "Histórico alterado pelo admin",
            "itens-TOTAL_FORMS": "0",
            "itens-INITIAL_FORMS": "0",
            "itens-MIN_NUM_FORMS": "0",
            "itens-MAX_NUM_FORMS": "1000",
            "_save": "Salvar",
        },
    )

    assert response.status_code == 403
    lancamento.refresh_from_db()
    assert lancamento.historico == "Histórico original"


# ---------------------------------------------------------------------------
# Achado novo 7 — ordenação do Diário observável independentemente do banco
# ---------------------------------------------------------------------------


def test_listar_diario_declara_ordenacao_por_data_criado_em_e_id(cenario):
    """Em vez de confiar que o banco, por acaso, devolve a ordem certa
    quando duas linhas têm `data` e `criado_em` iguais (o que fazia o teste
    antigo passar mesmo com o mutante S05 — `order_by` só por "data" — já
    que o PostgreSQL devolvia a ordem de inserção, coincidindo com o id
    neste cenário específico), verificamos a CLÁUSULA DE ORDENAÇÃO do
    próprio queryset — independente de como o banco decide desempatar.
    """
    queryset = listar_diario(
        empresa=cenario["empresa_a"], inicio=date(2024, 1, 1), fim=date(2024, 1, 31)
    )

    assert queryset.query.order_by == ("data", "criado_em", "id")


# ---------------------------------------------------------------------------
# Achado novo 10 — teto de consultas no Razão e na conferência
# ---------------------------------------------------------------------------


def test_razao_numero_de_consultas_tem_teto_explicito(
    client, cenario, django_assert_max_num_queries
):
    _autenticar(client, cenario["escritorio_a"])
    empresa = cenario["empresa_a"]
    periodo = {"inicio": "2024-01-01", "fim": "2024-01-31"}
    client.get(
        reverse("contabilidade:razao", args=[empresa.id, cenario["caixa"].id]), periodo
    )  # aquecimento

    with django_assert_max_num_queries(10):
        resposta = client.get(
            reverse("contabilidade:razao", args=[empresa.id, cenario["caixa"].id]), periodo
        )
    assert resposta.status_code == 200


def test_razao_numero_de_consultas_nao_cresce_com_tamanho_do_plano_de_contas(client, cenario):
    """Achados novos 10 e 14: o Razão de uma conta FOLHA não pode mais
    carregar o plano de contas inteiro da empresa — `_descendentes_de` só
    consulta a subárvore da conta pedida. Prova por comparação: o número de
    consultas do Razão de "Caixa" (folha, sem filhos) tem que ser o MESMO
    com 2 contas extra no plano e com 200.
    """
    _autenticar(client, cenario["escritorio_a"])
    empresa = cenario["empresa_a"]
    periodo = {"inicio": "2024-01-01", "fim": "2024-01-31"}
    client.get(
        reverse("contabilidade:razao", args=[empresa.id, cenario["caixa"].id]), periodo
    )  # aquecimento

    with CaptureQueriesContext(connection) as poucas_contas:
        client.get(reverse("contabilidade:razao", args=[empresa.id, cenario["caixa"].id]), periodo)

    for i in range(200):
        Conta.objects.create(
            empresa=empresa,
            codigo=f"9.{i}",
            nome=f"Conta extra {i}",
            tipo=TipoConta.ATIVO,
            natureza=NaturezaConta.DEVEDORA,
        )

    with CaptureQueriesContext(connection) as muitas_contas:
        client.get(reverse("contabilidade:razao", args=[empresa.id, cenario["caixa"].id]), periodo)

    assert len(muitas_contas) == len(poucas_contas)


def test_conferencia_numero_de_consultas_tem_teto_explicito(
    client, cenario, django_assert_max_num_queries
):
    _autenticar(client, cenario["escritorio_a"])
    empresa = cenario["empresa_a"]
    client.get(
        reverse("contabilidade:conferencia-lotes-desbalanceados", args=[empresa.id])
    )  # aquecimento

    with django_assert_max_num_queries(10):
        resposta = client.get(
            reverse("contabilidade:conferencia-lotes-desbalanceados", args=[empresa.id])
        )
    assert resposta.status_code == 200


# ---------------------------------------------------------------------------
# Achado novo 5 da rodada 3: os dois testes de teto acima NÃO DISCRIMINAM —
# passam com 201/201 mesmo removendo `select_related` do Razão (N+1
# garantido, M19) e não medem o custo real de um plano de contas profundo.
# ---------------------------------------------------------------------------


def test_razao_numero_de_consultas_nao_cresce_com_quantidade_de_itens(
    client, cenario, django_assert_max_num_queries
):
    """Mata M19 (remoção de `select_related("lancamento", "conta")` do
    Razão): com `select_related`, o número de consultas do Razão de uma
    conta FOLHA é CONSTANTE — não depende de quantos itens ela tem no
    período — porque lançamento e conta de cada item vêm no MESMO `JOIN`,
    não numa consulta por item (N+1). Medido: 60 lançamentos (60 itens na
    conta consultada) ainda ficam nas MESMAS ~8 consultas do teste de teto
    acima; sem `select_related`, o mesmo cenário sobe para ~121 (uma
    consulta por `item.lancamento` mais uma por `item.conta`) — bem acima do
    teto de 10 declarado no teste de teto. O teste anterior (achado 10 da
    rodada 2) não pegava isto porque o cenário de aquecimento tinha poucos
    ou nenhum item.
    """
    _autenticar(client, cenario["escritorio_a"])
    empresa = cenario["empresa_a"]
    periodo = {"inicio": "2024-01-01", "fim": "2024-01-31"}
    for i in range(60):
        criar_lancamento(
            empresa=empresa,
            data=date(2024, 1, 5),
            historico=f"Movimento {i}",
            itens=[
                {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("1.00")},
                {
                    "conta": cenario["capital"],
                    "tipo": TipoPartida.CREDITO,
                    "valor": Decimal("1.00"),
                },
            ],
        )
    client.get(
        reverse("contabilidade:razao", args=[empresa.id, cenario["caixa"].id]), periodo
    )  # aquecimento

    with django_assert_max_num_queries(10):
        resposta = client.get(
            reverse("contabilidade:razao", args=[empresa.id, cenario["caixa"].id]), periodo
        )
    assert resposta.status_code == 200


def test_razao_numero_de_consultas_do_grupo_raiz_de_plano_profundo(client, cenario):
    """Achado novo 5: o teto FIXO de 10 consultas só vale para conta FOLHA
    em plano RASO — `_descendentes_de` busca a subárvore da conta consultada
    NÍVEL A NÍVEL (uma consulta por nível de profundidade), então o Razão do
    grupo RAIZ de um plano profundo paga uma consulta por nível. Medido:
    profundidade 1 -> 8 consultas, 3 -> 10 (já no teto fixo), 6 -> 13, 10 ->
    17 — crescimento de uma consulta por nível, não uma explosão, mas
    incompatível com um teto FIXO de 10: um plano de contas brasileiro real
    tem 5 a 6 níveis. Este teste declara o teto em FUNÇÃO da profundidade
    (`profundidade + 9`, com margem) em vez de um número fixo que a
    hierarquia real ultrapassa, e mostra explicitamente que o teto fixo de
    10 não serve para este caso.
    """
    _autenticar(client, cenario["escritorio_a"])
    empresa = cenario["empresa_a"]
    periodo = {"inicio": "2024-01-01", "fim": "2024-01-31"}

    profundidade = 8
    raiz = None
    conta_pai = None
    for nivel in range(profundidade):
        conta_pai = Conta.objects.create(
            empresa=empresa,
            codigo=f"9.{nivel}",
            nome=f"Nível {nivel} do plano profundo",
            tipo=TipoConta.ATIVO,
            natureza=NaturezaConta.DEVEDORA,
            conta_pai=conta_pai,
        )
        if raiz is None:
            raiz = conta_pai

    client.get(reverse("contabilidade:razao", args=[empresa.id, raiz.id]), periodo)  # aquecimento
    with CaptureQueriesContext(connection) as ctx:
        resposta = client.get(reverse("contabilidade:razao", args=[empresa.id, raiz.id]), periodo)

    assert resposta.status_code == 200
    # O teto FIXO das duas funções acima (10) já não bastaria aqui — este é
    # exatamente o ponto do achado: declarar o teto em função da
    # profundidade, com uma margem pequena para não quebrar por 1 consulta
    # incidental de middleware/permissão.
    assert len(ctx) > 10
    assert len(ctx) <= profundidade + 9


def test_razao_nao_consolida_conta_de_outra_empresa_com_conta_pai_corrompido(client, cenario):
    """M05 (achado novo 6): `_descendentes_de` filtra por `empresa=empresa`
    ALÉM de `conta_pai_id__in` — sem esse filtro, uma conta de OUTRA
    empresa cujo `conta_pai` (só alcançável por gravação direta no ORM,
    contornando `Conta.clean()` — mesma via da auditoria) aponta para uma
    conta DESTA empresa apareceria no Razão consolidado como se fosse
    descendente legítima.

    O filtro a jusante (`lancamento__empresa=empresa` na consulta de itens
    de `apurar_razao`) sozinho NÃO bastaria para pegar este caso: aqui o
    item corrompido tem `conta` de uma empresa e `lancamento` da OUTRA (a
    consultada) — o mesmo tipo de corrupção que `ItemLancamento.clean()`
    recusa no caminho validado (achado 10 / achado novo 6 da rodada 2), só
    alcançável por ORM direto. Só o filtro por empresa DENTRO de
    `_descendentes_de` impede essa conta de entrar no conjunto de ids
    consolidados.
    """
    _autenticar(client, cenario["escritorio_a"])
    periodo = {"inicio": "2024-01-01", "fim": "2024-01-31"}

    # "Infiltrada" é da empresa B, mas o `conta_pai` aponta para "Caixa" da
    # empresa A — corrompido, só alcançável por ORM direto (`.create()` não
    # chama `full_clean()`).
    infiltrada = Conta.objects.create(
        empresa=cenario["empresa_b"],
        codigo="9.9",
        nome="Infiltrada",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        conta_pai=cenario["caixa"],
    )
    # O item corrompido tem `conta` da empresa B e `lancamento` da empresa A
    # (a consultada) — se `_descendentes_de` incluísse "infiltrada" por
    # engano, o filtro `lancamento__empresa=empresa` NÃO pegaria este item,
    # porque o lançamento É da empresa A.
    lancamento_a = LancamentoContabil.objects.create(
        empresa=cenario["empresa_a"], data=date(2024, 1, 5), historico="Lançamento da empresa A"
    )
    ItemLancamento.objects.create(
        lancamento=lancamento_a,
        conta=infiltrada,
        tipo=TipoPartida.DEBITO,
        valor=Decimal("999.99"),
    )

    resposta = client.get(
        reverse("contabilidade:razao", args=[cenario["empresa_a"].id, cenario["caixa"].id]),
        periodo,
    )

    assert resposta.status_code == 200
    razao = resposta.json()
    assert razao["total_debito"] == "0.00"
    assert all(item["valor"] != "999.99" for item in razao["itens"])


# ---------------------------------------------------------------------------
# Achado novo 13 — a conferência de hierarquia acumula TODAS as
# inconsistências, não só a primeira
# ---------------------------------------------------------------------------


def test_conferencia_aponta_todos_os_ciclos_independentes_da_hierarquia(client, cenario):
    empresa = cenario["empresa_a"]
    a1 = Conta.objects.create(
        empresa=empresa,
        codigo="A1",
        nome="A1",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    a2 = Conta.objects.create(
        empresa=empresa,
        codigo="A2",
        nome="A2",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        conta_pai=a1,
    )
    Conta.objects.filter(pk=a1.id).update(conta_pai=a2.id)  # ciclo A1 <-> A2

    b1 = Conta.objects.create(
        empresa=empresa,
        codigo="B1",
        nome="B1",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    b2 = Conta.objects.create(
        empresa=empresa,
        codigo="B2",
        nome="B2",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        conta_pai=b1,
    )
    Conta.objects.filter(pk=b1.id).update(conta_pai=b2.id)  # ciclo B1 <-> B2, INDEPENDENTE

    _autenticar(client, cenario["escritorio_a"])
    response = client.get(
        reverse("contabilidade:conferencia-lotes-desbalanceados", args=[empresa.id])
    )

    inconsistencias = response.json()["hierarquia_inconsistente"]
    assert len(inconsistencias) == 2
    texto = " ".join(inconsistencias)
    assert "A1" in texto
    assert "B1" in texto


# ---------------------------------------------------------------------------
# Achado novo 14 — ciclo em um ramo não derruba o Razão de conta sem
# relação; guarda de reclassificação não acusa quem não reclassificou
# ---------------------------------------------------------------------------


def test_razao_de_conta_sem_relacao_com_ciclo_continua_disponivel(client, cenario):
    """Um ciclo entre DUAS contas (sem relação com "Caixa") não pode mais
    derrubar o Razão de "Caixa" — antes desta correção, `apurar_razao`
    validava a árvore INTEIRA da empresa antes de decidir o que consolidar.
    """
    empresa = cenario["empresa_a"]
    x1 = Conta.objects.create(
        empresa=empresa,
        codigo="8",
        nome="X1",
        tipo=TipoConta.DESPESA,
        natureza=NaturezaConta.DEVEDORA,
    )
    x2 = Conta.objects.create(
        empresa=empresa,
        codigo="8.1",
        nome="X2",
        tipo=TipoConta.DESPESA,
        natureza=NaturezaConta.DEVEDORA,
        conta_pai=x1,
    )
    Conta.objects.filter(pk=x1.id).update(conta_pai=x2.id)  # ciclo x1 <-> x2

    _autenticar(client, cenario["escritorio_a"])
    response = client.get(
        reverse("contabilidade:razao", args=[empresa.id, cenario["caixa"].id]),
        {"inicio": "2024-01-01", "fim": "2024-01-31"},
    )

    assert response.status_code == 200


def test_conta_clean_nao_acusa_reclassificacao_em_edicao_que_nao_toca_aceita_lancamento(cenario):
    """Uma conta JÁ em estado legado (sintética com movimento, alcançada só
    por `.update()` direto no ORM — a mesma via da auditoria) não pode ter
    QUALQUER outra edição (aqui, renomear) bloqueada com uma mensagem que
    acusa o usuário de estar reclassificando, quando ele não tocou
    `aceita_lancamento` nesta gravação.
    """
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 5),
        historico="Lançamento",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("500.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("500.00")},
        ],
    )
    Conta.objects.filter(pk=cenario["caixa"].id).update(aceita_lancamento=False)  # estado legado

    caixa = Conta.objects.get(pk=cenario["caixa"].id)
    caixa.nome = "Caixa (renomeada)"  # não toca aceita_lancamento

    caixa.full_clean()  # não deve levantar
    caixa.save()

    assert Conta.objects.get(pk=caixa.id).nome == "Caixa (renomeada)"


def test_conta_clean_continua_recusando_a_transicao_real_para_sintetica(cenario):
    """Continua recusando quando a TRANSIÇÃO é real nesta gravação (estava
    True no banco, o `full_clean()` está mudando para False agora) — não é
    uma regressão do achado novo 14, é a checagem de que a guarda continua
    valendo para o caso que ela existe para impedir.
    """
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 5),
        historico="Lançamento",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("500.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("500.00")},
        ],
    )
    caixa = Conta.objects.get(pk=cenario["caixa"].id)
    caixa.aceita_lancamento = False

    with pytest.raises(ValidationError):
        caixa.full_clean()
