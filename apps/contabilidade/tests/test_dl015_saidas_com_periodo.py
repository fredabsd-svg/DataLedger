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


def _assert_toda_linha_do_balancete_bate_com_a_propria_natureza(response, empresa):
    """Teste GENÉRICO pedido pelo achado 3: para TODA linha do balancete,
    analítica ou sintética, `saldo_final == saldo_anterior ± (debitos −
    creditos)` conforme a NATUREZA DA PRÓPRIA CONTA (nunca a de um filho ou
    de outra linha) — lida direto do banco, sem depender da fixture.
    """
    naturezas_por_codigo = dict(
        Conta.objects.filter(empresa=empresa).values_list("codigo", "natureza")
    )
    for linha in response.json()["contas"]:
        saldo_anterior = Decimal(linha["saldo_anterior"])
        debitos = Decimal(linha["debitos"])
        creditos = Decimal(linha["creditos"])
        saldo_final = Decimal(linha["saldo_final"])
        sinal = 1 if naturezas_por_codigo[linha["conta"]] == NaturezaConta.DEVEDORA else -1
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
    assert lotes[lote_unico.id]["motivo"] == "sem_partidas"
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
    _usuario_com_papel(papel, cenario["escritorio_a"], f"usuario-{papel.value}")
    client.login(username=f"usuario-{papel.value}", password="senha-forte-123")
    periodo = {"inicio": "2024-01-01", "fim": "2024-01-31"}

    rotas = [
        reverse("contabilidade:diario", args=[cenario["empresa_a"].id]),
        reverse("contabilidade:razao", args=[cenario["empresa_a"].id, cenario["caixa"].id]),
        reverse("contabilidade:balancete", args=[cenario["empresa_a"].id]),
        reverse("contabilidade:conferencia-lotes-desbalanceados", args=[cenario["empresa_a"].id]),
    ]
    for rota in rotas:
        response = client.get(rota, periodo)
        assert response.status_code == status_esperado, rota


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
