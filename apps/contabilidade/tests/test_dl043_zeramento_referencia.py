"""DL-043, fatia 2 — casos de referência CALCULADOS À MÃO para o zeramento do
resultado (`apps.contabilidade.services.pre_visualizar_zeramento` e
`zerar_resultado`).

Este módulo cobre SÓ a conta (RC-104/RC-105): lucro, prejuízo, resultado
exatamente zero, só receita, só despesa, conta retificadora de receita,
centavos, correspondência periodicidade × mês de encerramento, e a
conciliação com o Balancete/PL. Concorrência, idempotência, permissão e
isolamento entre empresas são cobertos em outro arquivo, por outro
trabalhador — não duplicados aqui.

Cada teste nomeia, no docstring, a conta feita à mão ANTES de qualquer
chamada ao serviço — os números abaixo não são "o que o código devolveu",
são o valor independente que o código precisa bater. Dados 100% sintéticos.
"""

import itertools
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.contabilidade.models import (
    Conta,
    LancamentoContabil,
    NaturezaConta,
    PeriodicidadeZeramento,
    TipoConta,
    TipoPartida,
)
from apps.contabilidade.services import (
    ParametroContabilInvalido,
    apurar_balancete,
    apurar_saldos,
    criar_lancamento,
    pre_visualizar_zeramento,
    registrar_parametro_contabil,
    zerar_resultado,
)
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio

pytestmark = pytest.mark.django_db

D = NaturezaConta.DEVEDORA
C = NaturezaConta.CREDORA


# ---------------------------------------------------------------------------
# Fixtures e helpers — no molde de test_dl032_camada_de_saldos.py.
# ---------------------------------------------------------------------------

_CONTADOR_DE_CNPJ = itertools.count(1)


def _cnpj_sintetico():
    return f"{next(_CONTADOR_DE_CNPJ):014d}"


def _empresa(nome):
    escritorio = Escritorio.objects.create(nome=f"Escritório {nome}", cnpj=_cnpj_sintetico())
    return Empresa.objects.create(
        escritorio=escritorio, razao_social=f"{nome} Ltda", cnpj=_cnpj_sintetico()
    )


def _conta(empresa, *, codigo, nome, tipo, natureza, pai=None, aceita_lancamento=True):
    return Conta.objects.create(
        empresa=empresa,
        conta_pai=pai,
        codigo=codigo,
        nome=nome,
        tipo=tipo,
        natureza=natureza,
        aceita_lancamento=aceita_lancamento,
    )


def _plano_pl(empresa):
    """Caixa (para bater as partidas de movimento) + as TRÊS contas de
    destino do zeramento — Resultado do Exercício e Lucros Acumulados
    cadastradas CREDORAS (grupo PL); (-) Prejuízos Acumulados cadastrada
    DEVEDORA (RC-61: retificadora dentro de um grupo credor)."""
    return {
        "caixa": _conta(empresa, codigo="1.1", nome="Caixa", tipo=TipoConta.ATIVO, natureza=D),
        "resultado": _conta(
            empresa,
            codigo="3.4",
            nome="Resultado do Exercício",
            tipo=TipoConta.PATRIMONIO_LIQUIDO,
            natureza=C,
        ),
        "lucros": _conta(
            empresa,
            codigo="3.2",
            nome="Lucros Acumulados",
            tipo=TipoConta.PATRIMONIO_LIQUIDO,
            natureza=C,
        ),
        "prejuizos": _conta(
            empresa,
            codigo="3.3",
            nome="(-) Prejuízos Acumulados",
            tipo=TipoConta.PATRIMONIO_LIQUIDO,
            natureza=D,
        ),
    }


def _lancar(empresa, data, historico, debito, credito, valor, usuario=None):
    criar_lancamento(
        empresa=empresa,
        data=data,
        historico=historico,
        itens=[
            {"conta": debito, "tipo": TipoPartida.DEBITO, "valor": Decimal(valor)},
            {"conta": credito, "tipo": TipoPartida.CREDITO, "valor": Decimal(valor)},
        ],
        criado_por=usuario,
    )


def _registrar_parametro(
    empresa,
    plano,
    *,
    periodicidade=PeriodicidadeZeramento.MENSAL,
    vigencia_inicio=date(2026, 1, 1),
    usuario=None,
):
    return registrar_parametro_contabil(
        empresa=empresa,
        periodicidade_zeramento=periodicidade,
        conta_resultado_do_exercicio=plano["resultado"],
        conta_lucros_acumulados=plano["lucros"],
        conta_prejuizos_acumulados=plano["prejuizos"],
        vigencia_inicio=vigencia_inicio,
        usuario=usuario,
    )


def _itens_calculados(lista_de_itens):
    """Converte a lista `{"conta", "tipo", "valor"}` devolvida por
    `pre_visualizar_zeramento`/`_calcular_zeramento` num dict
    `{(codigo_da_conta, tipo): valor}` — comparável por igualdade sem
    depender da ORDEM em que o cálculo monta a lista."""
    return {(item["conta"].codigo, item["tipo"]): item["valor"] for item in lista_de_itens}


def _itens_do_lancamento(lancamento):
    """O mesmo formato de `_itens_calculados`, mas lido dos itens GRAVADOS
    (`lancamento.itens.all()`) — para conferir que a EXECUÇÃO real
    (`zerar_resultado`) gravou exatamente o que o cálculo previu."""
    return {(item.conta.codigo, item.tipo): item.valor for item in lancamento.itens.all()}


@pytest.fixture
def usuario():
    return get_user_model().objects.create_user(
        username="dl043-zeramento", email="dl043@escritorio.com.br", password="senha-forte-123"
    )


@pytest.fixture
def caso1_lucro(usuario):
    """Monta o cenário do Caso 1 (lucro), reutilizado pelos Casos 10 e 11
    (conciliação com Balancete e PL) — MESMO lucro de 6.000,00 conferido à
    mão no Caso 1, para não recalcular a conta duas vezes."""
    empresa = _empresa("DL-043 Caso1")
    plano = _plano_pl(empresa)
    receita = _conta(empresa, codigo="4.1", nome="Vendas", tipo=TipoConta.RECEITA, natureza=C)
    despesa = _conta(
        empresa, codigo="5.1", nome="Despesas Gerais", tipo=TipoConta.DESPESA, natureza=D
    )
    _registrar_parametro(empresa, plano, usuario=usuario)
    _lancar(empresa, date(2026, 1, 5), "Venda à vista", plano["caixa"], receita, "10000.00")
    _lancar(empresa, date(2026, 1, 10), "Pagamento de despesa", despesa, plano["caixa"], "4000.00")
    return {
        "empresa": empresa,
        "plano": plano,
        "receita": receita,
        "despesa": despesa,
        "usuario": usuario,
    }


# ---------------------------------------------------------------------------
# Caso 1 — Lucro.
#
# Receita credora, crédito 10.000,00; Despesa devedora, débito 4.000,00.
# Lucro = 10.000,00 − 4.000,00 = 6.000,00.
# Etapa 1: Receita débito 10.000,00; Despesa crédito 4.000,00; contrapartida
# Resultado do Exercício crédito 6.000,00 (fecha: 10.000 débito = 4.000 +
# 6.000 crédito).
# Etapa 2: Resultado do Exercício débito 6.000,00; Lucros Acumulados crédito
# 6.000,00; destino "lucros_acumulados".
# ---------------------------------------------------------------------------


def test_caso1_lucro_previa_calcula_sem_gravar(caso1_lucro):
    empresa = caso1_lucro["empresa"]
    plano = caso1_lucro["plano"]
    receita = caso1_lucro["receita"]
    despesa = caso1_lucro["despesa"]

    antes = LancamentoContabil.objects.count()
    previa = pre_visualizar_zeramento(empresa=empresa, ano=2026, mes=1)
    assert LancamentoContabil.objects.count() == antes  # a prévia NÃO grava nada

    assert previa["data_final"] == date(2026, 1, 31)
    assert _itens_calculados(previa["itens_etapa1"]) == {
        (receita.codigo, TipoPartida.DEBITO): Decimal("10000.00"),
        (despesa.codigo, TipoPartida.CREDITO): Decimal("4000.00"),
    }
    assert previa["item_resultado_etapa1"] == {
        "conta": plano["resultado"],
        "tipo": TipoPartida.CREDITO,
        "valor": Decimal("6000.00"),
    }
    etapa2 = previa["etapa2"]
    assert etapa2["destino"] == "lucros_acumulados"
    assert etapa2["item_resultado"] == {
        "conta": plano["resultado"],
        "tipo": TipoPartida.DEBITO,
        "valor": Decimal("6000.00"),
    }
    assert etapa2["item_destino"] == {
        "conta": plano["lucros"],
        "tipo": TipoPartida.CREDITO,
        "valor": Decimal("6000.00"),
    }


def test_caso1_lucro_execucao_grava_os_dois_lancamentos(caso1_lucro):
    empresa = caso1_lucro["empresa"]
    plano = caso1_lucro["plano"]
    receita = caso1_lucro["receita"]
    despesa = caso1_lucro["despesa"]
    usuario = caso1_lucro["usuario"]

    resultado = zerar_resultado(empresa=empresa, ano=2026, mes=1, usuario=usuario)

    assert resultado["data_final"] == date(2026, 1, 31)
    assert resultado["criado_etapa1"] is True
    assert resultado["criado_etapa2"] is True
    assert resultado["destino_etapa2"] == "lucros_acumulados"

    itens1 = _itens_do_lancamento(resultado["lancamento_etapa1"])
    assert itens1 == {
        (receita.codigo, TipoPartida.DEBITO): Decimal("10000.00"),
        (despesa.codigo, TipoPartida.CREDITO): Decimal("4000.00"),
        (plano["resultado"].codigo, TipoPartida.CREDITO): Decimal("6000.00"),
    }
    itens2 = _itens_do_lancamento(resultado["lancamento_etapa2"])
    assert itens2 == {
        (plano["resultado"].codigo, TipoPartida.DEBITO): Decimal("6000.00"),
        (plano["lucros"].codigo, TipoPartida.CREDITO): Decimal("6000.00"),
    }


# ---------------------------------------------------------------------------
# Caso 2 — Prejuízo.
#
# Receita credora, crédito 3.000,00; Despesa devedora, débito 5.000,00.
# Prejuízo = 3.000,00 − 5.000,00 = −2.000,00 (prejuízo de 2.000,00).
# Etapa 1: Receita débito 3.000,00; Despesa crédito 5.000,00; contrapartida
# Resultado do Exercício DÉBITO 2.000,00 (fecha: 3.000+2.000 débito = 5.000
# crédito).
# Etapa 2: Resultado do Exercício CRÉDITO 2.000,00; (-) Prejuízos Acumulados
# DÉBITO 2.000,00; destino "prejuizos_acumulados".
# ---------------------------------------------------------------------------


def test_caso2_prejuizo_previa_calcula_sem_gravar(usuario):
    empresa = _empresa("DL-043 Caso2")
    plano = _plano_pl(empresa)
    receita = _conta(empresa, codigo="4.1", nome="Vendas", tipo=TipoConta.RECEITA, natureza=C)
    despesa = _conta(
        empresa, codigo="5.1", nome="Despesas Gerais", tipo=TipoConta.DESPESA, natureza=D
    )
    _registrar_parametro(empresa, plano, usuario=usuario)
    _lancar(empresa, date(2026, 1, 5), "Venda à vista", plano["caixa"], receita, "3000.00")
    _lancar(empresa, date(2026, 1, 10), "Pagamento de despesa", despesa, plano["caixa"], "5000.00")

    antes = LancamentoContabil.objects.count()
    previa = pre_visualizar_zeramento(empresa=empresa, ano=2026, mes=1)
    assert LancamentoContabil.objects.count() == antes

    assert _itens_calculados(previa["itens_etapa1"]) == {
        (receita.codigo, TipoPartida.DEBITO): Decimal("3000.00"),
        (despesa.codigo, TipoPartida.CREDITO): Decimal("5000.00"),
    }
    assert previa["item_resultado_etapa1"] == {
        "conta": plano["resultado"],
        "tipo": TipoPartida.DEBITO,
        "valor": Decimal("2000.00"),
    }
    etapa2 = previa["etapa2"]
    assert etapa2["destino"] == "prejuizos_acumulados"
    assert etapa2["item_resultado"] == {
        "conta": plano["resultado"],
        "tipo": TipoPartida.CREDITO,
        "valor": Decimal("2000.00"),
    }
    assert etapa2["item_destino"] == {
        "conta": plano["prejuizos"],
        "tipo": TipoPartida.DEBITO,
        "valor": Decimal("2000.00"),
    }


def test_caso2_prejuizo_execucao_grava_os_dois_lancamentos(usuario):
    empresa = _empresa("DL-043 Caso2 Execução")
    plano = _plano_pl(empresa)
    receita = _conta(empresa, codigo="4.1", nome="Vendas", tipo=TipoConta.RECEITA, natureza=C)
    despesa = _conta(
        empresa, codigo="5.1", nome="Despesas Gerais", tipo=TipoConta.DESPESA, natureza=D
    )
    _registrar_parametro(empresa, plano, usuario=usuario)
    _lancar(empresa, date(2026, 1, 5), "Venda à vista", plano["caixa"], receita, "3000.00")
    _lancar(empresa, date(2026, 1, 10), "Pagamento de despesa", despesa, plano["caixa"], "5000.00")

    resultado = zerar_resultado(empresa=empresa, ano=2026, mes=1, usuario=usuario)

    assert resultado["destino_etapa2"] == "prejuizos_acumulados"
    itens1 = _itens_do_lancamento(resultado["lancamento_etapa1"])
    assert itens1 == {
        (receita.codigo, TipoPartida.DEBITO): Decimal("3000.00"),
        (despesa.codigo, TipoPartida.CREDITO): Decimal("5000.00"),
        (plano["resultado"].codigo, TipoPartida.DEBITO): Decimal("2000.00"),
    }
    itens2 = _itens_do_lancamento(resultado["lancamento_etapa2"])
    assert itens2 == {
        (plano["resultado"].codigo, TipoPartida.CREDITO): Decimal("2000.00"),
        (plano["prejuizos"].codigo, TipoPartida.DEBITO): Decimal("2000.00"),
    }


# ---------------------------------------------------------------------------
# Caso 3 — Resultado exatamente zero.
#
# Receita credora, crédito 5.000,00; Despesa devedora, débito 5.000,00.
# Etapa 1 AINDA acontece (as duas contas têm saldo próprio a zerar): Receita
# débito 5.000,00, Despesa crédito 5.000,00 — e elas já FECHAM entre si
# (5.000 débito = 5.000 crédito), então NENHUM item de contrapartida em
# Resultado é necessário nem permitido.
# Etapa 2 NÃO acontece: sem contrapartida, o saldo de Resultado do Exercício
# permanece zero.
# ---------------------------------------------------------------------------


def test_caso3_resultado_zero_previa_zera_receita_e_despesa_sem_contrapartida(usuario):
    empresa = _empresa("DL-043 Caso3")
    plano = _plano_pl(empresa)
    receita = _conta(empresa, codigo="4.1", nome="Vendas", tipo=TipoConta.RECEITA, natureza=C)
    despesa = _conta(
        empresa, codigo="5.1", nome="Despesas Gerais", tipo=TipoConta.DESPESA, natureza=D
    )
    _registrar_parametro(empresa, plano, usuario=usuario)
    _lancar(empresa, date(2026, 1, 5), "Venda à vista", plano["caixa"], receita, "5000.00")
    _lancar(empresa, date(2026, 1, 10), "Pagamento de despesa", despesa, plano["caixa"], "5000.00")

    antes = LancamentoContabil.objects.count()
    previa = pre_visualizar_zeramento(empresa=empresa, ano=2026, mes=1)
    assert LancamentoContabil.objects.count() == antes

    assert _itens_calculados(previa["itens_etapa1"]) == {
        (receita.codigo, TipoPartida.DEBITO): Decimal("5000.00"),
        (despesa.codigo, TipoPartida.CREDITO): Decimal("5000.00"),
    }
    assert previa["item_resultado_etapa1"] is None
    assert previa["etapa2"] is None


def test_caso3_resultado_zero_execucao_grava_so_a_etapa1(usuario):
    empresa = _empresa("DL-043 Caso3 Execução")
    plano = _plano_pl(empresa)
    receita = _conta(empresa, codigo="4.1", nome="Vendas", tipo=TipoConta.RECEITA, natureza=C)
    despesa = _conta(
        empresa, codigo="5.1", nome="Despesas Gerais", tipo=TipoConta.DESPESA, natureza=D
    )
    _registrar_parametro(empresa, plano, usuario=usuario)
    _lancar(empresa, date(2026, 1, 5), "Venda à vista", plano["caixa"], receita, "5000.00")
    _lancar(empresa, date(2026, 1, 10), "Pagamento de despesa", despesa, plano["caixa"], "5000.00")

    resultado = zerar_resultado(empresa=empresa, ano=2026, mes=1, usuario=usuario)

    assert resultado["criado_etapa1"] is True
    itens1 = _itens_do_lancamento(resultado["lancamento_etapa1"])
    assert itens1 == {
        (receita.codigo, TipoPartida.DEBITO): Decimal("5000.00"),
        (despesa.codigo, TipoPartida.CREDITO): Decimal("5000.00"),
    }
    assert resultado["lancamento_etapa2"] is None
    assert resultado["criado_etapa2"] is False
    assert resultado["destino_etapa2"] is None


# ---------------------------------------------------------------------------
# Caso 4 — Só receitas (nenhuma despesa cadastrada/com movimento).
#
# Receita credora, crédito 7.000,00. Etapa 1: Receita débito 7.000,00,
# contrapartida Resultado do Exercício crédito 7.000,00. Etapa 2: transfere
# 7.000,00 para Lucros Acumulados.
# ---------------------------------------------------------------------------


def test_caso4_so_receitas_previa_calcula_sem_gravar(usuario):
    empresa = _empresa("DL-043 Caso4")
    plano = _plano_pl(empresa)
    receita = _conta(empresa, codigo="4.1", nome="Vendas", tipo=TipoConta.RECEITA, natureza=C)
    _registrar_parametro(empresa, plano, usuario=usuario)
    _lancar(empresa, date(2026, 1, 5), "Venda à vista", plano["caixa"], receita, "7000.00")

    antes = LancamentoContabil.objects.count()
    previa = pre_visualizar_zeramento(empresa=empresa, ano=2026, mes=1)
    assert LancamentoContabil.objects.count() == antes

    assert _itens_calculados(previa["itens_etapa1"]) == {
        (receita.codigo, TipoPartida.DEBITO): Decimal("7000.00"),
    }
    assert previa["item_resultado_etapa1"] == {
        "conta": plano["resultado"],
        "tipo": TipoPartida.CREDITO,
        "valor": Decimal("7000.00"),
    }
    etapa2 = previa["etapa2"]
    assert etapa2["destino"] == "lucros_acumulados"
    assert etapa2["item_destino"] == {
        "conta": plano["lucros"],
        "tipo": TipoPartida.CREDITO,
        "valor": Decimal("7000.00"),
    }


def test_caso4_so_receitas_execucao_grava_os_dois_lancamentos(usuario):
    empresa = _empresa("DL-043 Caso4 Execução")
    plano = _plano_pl(empresa)
    receita = _conta(empresa, codigo="4.1", nome="Vendas", tipo=TipoConta.RECEITA, natureza=C)
    _registrar_parametro(empresa, plano, usuario=usuario)
    _lancar(empresa, date(2026, 1, 5), "Venda à vista", plano["caixa"], receita, "7000.00")

    resultado = zerar_resultado(empresa=empresa, ano=2026, mes=1, usuario=usuario)

    assert resultado["destino_etapa2"] == "lucros_acumulados"
    itens1 = _itens_do_lancamento(resultado["lancamento_etapa1"])
    assert itens1 == {
        (receita.codigo, TipoPartida.DEBITO): Decimal("7000.00"),
        (plano["resultado"].codigo, TipoPartida.CREDITO): Decimal("7000.00"),
    }
    itens2 = _itens_do_lancamento(resultado["lancamento_etapa2"])
    assert itens2 == {
        (plano["resultado"].codigo, TipoPartida.DEBITO): Decimal("7000.00"),
        (plano["lucros"].codigo, TipoPartida.CREDITO): Decimal("7000.00"),
    }


# ---------------------------------------------------------------------------
# Caso 5 — Só despesas (nenhuma receita cadastrada/com movimento).
#
# Despesa devedora, débito 2.500,00. Etapa 1: Despesa crédito 2.500,00,
# contrapartida Resultado do Exercício débito 2.500,00. Etapa 2: transfere
# 2.500,00 para (-) Prejuízos Acumulados.
# ---------------------------------------------------------------------------


def test_caso5_so_despesas_previa_calcula_sem_gravar(usuario):
    empresa = _empresa("DL-043 Caso5")
    plano = _plano_pl(empresa)
    despesa = _conta(
        empresa, codigo="5.1", nome="Despesas Gerais", tipo=TipoConta.DESPESA, natureza=D
    )
    _registrar_parametro(empresa, plano, usuario=usuario)
    _lancar(empresa, date(2026, 1, 10), "Pagamento de despesa", despesa, plano["caixa"], "2500.00")

    antes = LancamentoContabil.objects.count()
    previa = pre_visualizar_zeramento(empresa=empresa, ano=2026, mes=1)
    assert LancamentoContabil.objects.count() == antes

    assert _itens_calculados(previa["itens_etapa1"]) == {
        (despesa.codigo, TipoPartida.CREDITO): Decimal("2500.00"),
    }
    assert previa["item_resultado_etapa1"] == {
        "conta": plano["resultado"],
        "tipo": TipoPartida.DEBITO,
        "valor": Decimal("2500.00"),
    }
    etapa2 = previa["etapa2"]
    assert etapa2["destino"] == "prejuizos_acumulados"
    assert etapa2["item_destino"] == {
        "conta": plano["prejuizos"],
        "tipo": TipoPartida.DEBITO,
        "valor": Decimal("2500.00"),
    }


def test_caso5_so_despesas_execucao_grava_os_dois_lancamentos(usuario):
    empresa = _empresa("DL-043 Caso5 Execução")
    plano = _plano_pl(empresa)
    despesa = _conta(
        empresa, codigo="5.1", nome="Despesas Gerais", tipo=TipoConta.DESPESA, natureza=D
    )
    _registrar_parametro(empresa, plano, usuario=usuario)
    _lancar(empresa, date(2026, 1, 10), "Pagamento de despesa", despesa, plano["caixa"], "2500.00")

    resultado = zerar_resultado(empresa=empresa, ano=2026, mes=1, usuario=usuario)

    assert resultado["destino_etapa2"] == "prejuizos_acumulados"
    itens1 = _itens_do_lancamento(resultado["lancamento_etapa1"])
    assert itens1 == {
        (despesa.codigo, TipoPartida.CREDITO): Decimal("2500.00"),
        (plano["resultado"].codigo, TipoPartida.DEBITO): Decimal("2500.00"),
    }
    itens2 = _itens_do_lancamento(resultado["lancamento_etapa2"])
    assert itens2 == {
        (plano["resultado"].codigo, TipoPartida.CREDITO): Decimal("2500.00"),
        (plano["prejuizos"].codigo, TipoPartida.DEBITO): Decimal("2500.00"),
    }


# ---------------------------------------------------------------------------
# Caso 6 — Conta retificadora de receita (devoluções de vendas).
#
# Vendas (RECEITA, credora): crédito 10.000,00. (-) Devoluções de Vendas
# (RECEITA, DEVEDORA — retificadora): débito 1.000,00. Custos (DESPESA,
# devedora): débito 3.000,00.
# Lucro = 10.000,00 − 1.000,00 − 3.000,00 = 6.000,00.
# Etapa 1: Vendas débito 10.000,00 (zera o saldo credor); Devoluções CRÉDITO
# 1.000,00 (o sinal é INVERTIDO em relação a Vendas, porque a natureza
# cadastrada é devedora — o saldo de 1.000,00 devedor também é zerado a
# crédito); Custos crédito 3.000,00; contrapartida Resultado do Exercício
# crédito 6.000,00 (fecha: 10.000 débito = 1.000+3.000+6.000 crédito).
# Etapa 2: transfere 6.000,00 para Lucros Acumulados.
# ---------------------------------------------------------------------------


def test_caso6_retificadora_de_receita_previa_calcula_sem_gravar(usuario):
    empresa = _empresa("DL-043 Caso6")
    plano = _plano_pl(empresa)
    vendas = _conta(empresa, codigo="4.1", nome="Vendas", tipo=TipoConta.RECEITA, natureza=C)
    devolucoes = _conta(
        empresa,
        codigo="4.2",
        nome="(-) Devoluções de Vendas",
        tipo=TipoConta.RECEITA,
        natureza=D,  # retificadora: natureza OPOSTA ao grupo (Receita é credora)
    )
    custos = _conta(empresa, codigo="5.1", nome="Custos", tipo=TipoConta.DESPESA, natureza=D)
    _registrar_parametro(empresa, plano, usuario=usuario)
    _lancar(empresa, date(2026, 1, 5), "Venda à vista", plano["caixa"], vendas, "10000.00")
    _lancar(empresa, date(2026, 1, 8), "Devolução de venda", devolucoes, plano["caixa"], "1000.00")
    _lancar(empresa, date(2026, 1, 10), "Pagamento de custo", custos, plano["caixa"], "3000.00")

    antes = LancamentoContabil.objects.count()
    previa = pre_visualizar_zeramento(empresa=empresa, ano=2026, mes=1)
    assert LancamentoContabil.objects.count() == antes

    assert _itens_calculados(previa["itens_etapa1"]) == {
        (vendas.codigo, TipoPartida.DEBITO): Decimal("10000.00"),
        (devolucoes.codigo, TipoPartida.CREDITO): Decimal("1000.00"),
        (custos.codigo, TipoPartida.CREDITO): Decimal("3000.00"),
    }
    assert previa["item_resultado_etapa1"] == {
        "conta": plano["resultado"],
        "tipo": TipoPartida.CREDITO,
        "valor": Decimal("6000.00"),
    }
    etapa2 = previa["etapa2"]
    assert etapa2["destino"] == "lucros_acumulados"
    assert etapa2["item_destino"] == {
        "conta": plano["lucros"],
        "tipo": TipoPartida.CREDITO,
        "valor": Decimal("6000.00"),
    }


def test_caso6_retificadora_de_receita_execucao_grava_tres_itens_na_etapa1(usuario):
    empresa = _empresa("DL-043 Caso6 Execução")
    plano = _plano_pl(empresa)
    vendas = _conta(empresa, codigo="4.1", nome="Vendas", tipo=TipoConta.RECEITA, natureza=C)
    devolucoes = _conta(
        empresa,
        codigo="4.2",
        nome="(-) Devoluções de Vendas",
        tipo=TipoConta.RECEITA,
        natureza=D,
    )
    custos = _conta(empresa, codigo="5.1", nome="Custos", tipo=TipoConta.DESPESA, natureza=D)
    _registrar_parametro(empresa, plano, usuario=usuario)
    _lancar(empresa, date(2026, 1, 5), "Venda à vista", plano["caixa"], vendas, "10000.00")
    _lancar(empresa, date(2026, 1, 8), "Devolução de venda", devolucoes, plano["caixa"], "1000.00")
    _lancar(empresa, date(2026, 1, 10), "Pagamento de custo", custos, plano["caixa"], "3000.00")

    resultado = zerar_resultado(empresa=empresa, ano=2026, mes=1, usuario=usuario)

    itens1 = _itens_do_lancamento(resultado["lancamento_etapa1"])
    assert itens1 == {
        (vendas.codigo, TipoPartida.DEBITO): Decimal("10000.00"),
        (devolucoes.codigo, TipoPartida.CREDITO): Decimal("1000.00"),
        (custos.codigo, TipoPartida.CREDITO): Decimal("3000.00"),
        (plano["resultado"].codigo, TipoPartida.CREDITO): Decimal("6000.00"),
    }
    itens2 = _itens_do_lancamento(resultado["lancamento_etapa2"])
    assert itens2 == {
        (plano["resultado"].codigo, TipoPartida.DEBITO): Decimal("6000.00"),
        (plano["lucros"].codigo, TipoPartida.CREDITO): Decimal("6000.00"),
    }


# ---------------------------------------------------------------------------
# Caso 7 — Centavos, precisão Decimal exata.
#
# Receita credora, crédito 100,01; Despesa devedora, débito 33,34.
# Lucro = 100,01 − 33,34 = 66,67 (subtração exata em Decimal, sem
# arredondamento binário).
# ---------------------------------------------------------------------------


def test_caso7_centavos_previa_calcula_com_decimal_exato(usuario):
    empresa = _empresa("DL-043 Caso7")
    plano = _plano_pl(empresa)
    receita = _conta(empresa, codigo="4.1", nome="Vendas", tipo=TipoConta.RECEITA, natureza=C)
    despesa = _conta(
        empresa, codigo="5.1", nome="Despesas Gerais", tipo=TipoConta.DESPESA, natureza=D
    )
    _registrar_parametro(empresa, plano, usuario=usuario)
    _lancar(empresa, date(2026, 1, 5), "Venda à vista", plano["caixa"], receita, "100.01")
    _lancar(empresa, date(2026, 1, 10), "Pagamento de despesa", despesa, plano["caixa"], "33.34")

    previa = pre_visualizar_zeramento(empresa=empresa, ano=2026, mes=1)

    assert previa["item_resultado_etapa1"]["valor"] == Decimal("66.67")
    assert repr(previa["item_resultado_etapa1"]["valor"]) == "Decimal('66.67')"
    etapa2 = previa["etapa2"]
    assert etapa2["destino"] == "lucros_acumulados"
    assert etapa2["item_destino"]["valor"] == Decimal("66.67")


def test_caso7_centavos_execucao_grava_valor_exato(usuario):
    empresa = _empresa("DL-043 Caso7 Execução")
    plano = _plano_pl(empresa)
    receita = _conta(empresa, codigo="4.1", nome="Vendas", tipo=TipoConta.RECEITA, natureza=C)
    despesa = _conta(
        empresa, codigo="5.1", nome="Despesas Gerais", tipo=TipoConta.DESPESA, natureza=D
    )
    _registrar_parametro(empresa, plano, usuario=usuario)
    _lancar(empresa, date(2026, 1, 5), "Venda à vista", plano["caixa"], receita, "100.01")
    _lancar(empresa, date(2026, 1, 10), "Pagamento de despesa", despesa, plano["caixa"], "33.34")

    resultado = zerar_resultado(empresa=empresa, ano=2026, mes=1, usuario=usuario)

    itens2 = _itens_do_lancamento(resultado["lancamento_etapa2"])
    assert itens2[(plano["lucros"].codigo, TipoPartida.CREDITO)] == Decimal("66.67")


# ---------------------------------------------------------------------------
# Caso 8 — Periodicidade TRIMESTRAL: só fecha em março/junho/setembro/
# dezembro.
#
# Receita credora, crédito 8.000,00 (jan); Despesa devedora, débito 3.000,00
# (fev). Lucro do trimestre = 5.000,00, só apurável em mes=3 (fim do
# trimestre) — mes=1 e mes=2, isolados, são recusados.
# ---------------------------------------------------------------------------


def test_caso8_trimestral_recusa_mes_fora_do_encerramento_sem_gravar(usuario):
    empresa = _empresa("DL-043 Caso8")
    plano = _plano_pl(empresa)
    receita = _conta(empresa, codigo="4.1", nome="Vendas", tipo=TipoConta.RECEITA, natureza=C)
    despesa = _conta(
        empresa, codigo="5.1", nome="Despesas Gerais", tipo=TipoConta.DESPESA, natureza=D
    )
    _registrar_parametro(
        empresa, plano, periodicidade=PeriodicidadeZeramento.TRIMESTRAL, usuario=usuario
    )
    _lancar(empresa, date(2026, 1, 15), "Venda à vista", plano["caixa"], receita, "8000.00")
    _lancar(empresa, date(2026, 2, 10), "Pagamento de despesa", despesa, plano["caixa"], "3000.00")

    antes = LancamentoContabil.objects.count()
    with pytest.raises(ParametroContabilInvalido):
        zerar_resultado(empresa=empresa, ano=2026, mes=2, usuario=usuario)
    assert LancamentoContabil.objects.count() == antes  # recusado ANTES de gravar

    with pytest.raises(ParametroContabilInvalido):
        pre_visualizar_zeramento(empresa=empresa, ano=2026, mes=1)
    assert LancamentoContabil.objects.count() == antes


def test_caso8_trimestral_aceita_o_mes_de_encerramento(usuario):
    empresa = _empresa("DL-043 Caso8 Válido")
    plano = _plano_pl(empresa)
    receita = _conta(empresa, codigo="4.1", nome="Vendas", tipo=TipoConta.RECEITA, natureza=C)
    despesa = _conta(
        empresa, codigo="5.1", nome="Despesas Gerais", tipo=TipoConta.DESPESA, natureza=D
    )
    _registrar_parametro(
        empresa, plano, periodicidade=PeriodicidadeZeramento.TRIMESTRAL, usuario=usuario
    )
    _lancar(empresa, date(2026, 1, 15), "Venda à vista", plano["caixa"], receita, "8000.00")
    _lancar(empresa, date(2026, 2, 10), "Pagamento de despesa", despesa, plano["caixa"], "3000.00")

    previa = pre_visualizar_zeramento(empresa=empresa, ano=2026, mes=3)
    assert previa["data_final"] == date(2026, 3, 31)
    assert previa["item_resultado_etapa1"] == {
        "conta": plano["resultado"],
        "tipo": TipoPartida.CREDITO,
        "valor": Decimal("5000.00"),
    }
    assert previa["etapa2"]["destino"] == "lucros_acumulados"

    resultado = zerar_resultado(empresa=empresa, ano=2026, mes=3, usuario=usuario)
    assert resultado["data_final"] == date(2026, 3, 31)
    assert resultado["criado_etapa1"] is True
    assert resultado["criado_etapa2"] is True
    assert resultado["destino_etapa2"] == "lucros_acumulados"
    itens2 = _itens_do_lancamento(resultado["lancamento_etapa2"])
    assert itens2[(plano["lucros"].codigo, TipoPartida.CREDITO)] == Decimal("5000.00")


# ---------------------------------------------------------------------------
# Caso 9 — Periodicidade ANUAL: só fecha em dezembro.
#
# Receita credora, crédito 9.000,00 (jun); Despesa devedora, débito 4.000,00
# (ago). Lucro do exercício = 5.000,00, só apurável em mes=12 — mes=11,
# isolado, é recusado.
#
# Datado em 2025 (não 2026, como os demais casos): dezembro de 2026 ainda
# não chegou (hoje é 2026-09-26) e cairia fora da faixa aceita pelo RC-77
# (até hoje + 30 dias) — 2025 fica inteiramente no passado e não tropeça
# nessa faixa em nenhum dos dois meses testados.
# ---------------------------------------------------------------------------


def test_caso9_anual_recusa_mes_diferente_de_dezembro_sem_gravar(usuario):
    empresa = _empresa("DL-043 Caso9")
    plano = _plano_pl(empresa)
    receita = _conta(empresa, codigo="4.1", nome="Vendas", tipo=TipoConta.RECEITA, natureza=C)
    despesa = _conta(
        empresa, codigo="5.1", nome="Despesas Gerais", tipo=TipoConta.DESPESA, natureza=D
    )
    _registrar_parametro(
        empresa,
        plano,
        periodicidade=PeriodicidadeZeramento.ANUAL,
        vigencia_inicio=date(2025, 1, 1),
        usuario=usuario,
    )
    _lancar(empresa, date(2025, 6, 15), "Venda à vista", plano["caixa"], receita, "9000.00")
    _lancar(empresa, date(2025, 8, 10), "Pagamento de despesa", despesa, plano["caixa"], "4000.00")

    antes = LancamentoContabil.objects.count()
    with pytest.raises(ParametroContabilInvalido):
        zerar_resultado(empresa=empresa, ano=2025, mes=11, usuario=usuario)
    assert LancamentoContabil.objects.count() == antes

    with pytest.raises(ParametroContabilInvalido):
        pre_visualizar_zeramento(empresa=empresa, ano=2025, mes=11)
    assert LancamentoContabil.objects.count() == antes


def test_caso9_anual_aceita_dezembro(usuario):
    empresa = _empresa("DL-043 Caso9 Válido")
    plano = _plano_pl(empresa)
    receita = _conta(empresa, codigo="4.1", nome="Vendas", tipo=TipoConta.RECEITA, natureza=C)
    despesa = _conta(
        empresa, codigo="5.1", nome="Despesas Gerais", tipo=TipoConta.DESPESA, natureza=D
    )
    _registrar_parametro(
        empresa,
        plano,
        periodicidade=PeriodicidadeZeramento.ANUAL,
        vigencia_inicio=date(2025, 1, 1),
        usuario=usuario,
    )
    _lancar(empresa, date(2025, 6, 15), "Venda à vista", plano["caixa"], receita, "9000.00")
    _lancar(empresa, date(2025, 8, 10), "Pagamento de despesa", despesa, plano["caixa"], "4000.00")

    previa = pre_visualizar_zeramento(empresa=empresa, ano=2025, mes=12)
    assert previa["data_final"] == date(2025, 12, 31)
    assert previa["item_resultado_etapa1"] == {
        "conta": plano["resultado"],
        "tipo": TipoPartida.CREDITO,
        "valor": Decimal("5000.00"),
    }
    assert previa["etapa2"]["destino"] == "lucros_acumulados"

    resultado = zerar_resultado(empresa=empresa, ano=2025, mes=12, usuario=usuario)
    assert resultado["data_final"] == date(2025, 12, 31)
    assert resultado["criado_etapa1"] is True
    assert resultado["criado_etapa2"] is True
    itens2 = _itens_do_lancamento(resultado["lancamento_etapa2"])
    assert itens2[(plano["lucros"].codigo, TipoPartida.CREDITO)] == Decimal("5000.00")


# ---------------------------------------------------------------------------
# Caso 10 — Conciliação com o Balancete: débitos = créditos, antes E depois.
# Reusa o lucro de 6.000,00 do Caso 1.
# ---------------------------------------------------------------------------


def test_caso10_balancete_fecha_antes_e_depois_do_zeramento(caso1_lucro):
    empresa = caso1_lucro["empresa"]
    usuario = caso1_lucro["usuario"]
    inicio = date(2000, 1, 1)
    fim = date(2026, 1, 31)

    antes = apurar_balancete(empresa=empresa, inicio=inicio, fim=fim)
    assert antes["total_debitos"] == antes["total_creditos"]

    zerar_resultado(empresa=empresa, ano=2026, mes=1, usuario=usuario)

    depois = apurar_balancete(empresa=empresa, inicio=inicio, fim=fim)
    assert depois["total_debitos"] == depois["total_creditos"]
    # Os DOIS lançamentos de zeramento também batem débito=crédito, então o
    # total sobe — o balancete não "absorve" a diferença em silêncio.
    assert depois["total_debitos"] > antes["total_debitos"]


# ---------------------------------------------------------------------------
# Caso 11 — A variação do saldo do PL bate com o resultado apurado.
# Reusa o lucro de 6.000,00 do Caso 1: soma de Resultado do Exercício +
# Lucros Acumulados + (-) Prejuízos Acumulados, ANTES (0,00, nada lançado
# ainda nessas contas) e DEPOIS (6.000,00, todo ele em Lucros Acumulados,
# porque Resultado do Exercício volta a zero na etapa 2) do zeramento.
# ---------------------------------------------------------------------------


def test_caso11_variacao_do_pl_bate_com_o_resultado_apurado(caso1_lucro):
    empresa = caso1_lucro["empresa"]
    plano = caso1_lucro["plano"]
    usuario = caso1_lucro["usuario"]
    data_final = date(2026, 1, 31)
    codigos_pl = {plano["resultado"].codigo, plano["lucros"].codigo, plano["prejuizos"].codigo}

    def _soma_pl(saldos):
        return sum(
            (linha["saldo"] for linha in saldos["contas"] if linha["conta"] in codigos_pl),
            Decimal("0"),
        )

    antes = apurar_saldos(empresa=empresa, data_base=data_final)
    pl_antes = _soma_pl(antes)
    assert pl_antes == Decimal("0.00")  # nada lançado ainda nas três contas de PL do zeramento

    zerar_resultado(empresa=empresa, ano=2026, mes=1, usuario=usuario)

    depois = apurar_saldos(empresa=empresa, data_base=data_final)
    pl_depois = _soma_pl(depois)

    # Lucro de 6.000,00 (Caso 1) SOMA ao PL — a variação bate, em módulo e
    # sinal, com o resultado apurado à mão.
    assert pl_depois - pl_antes == Decimal("6000.00")
