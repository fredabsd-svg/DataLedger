"""Testes do DL-008: sinal, escala e limites de entrada da escrituração manual.

Fecha o achado 4 da auditoria de 2026-09-11 (BL-17) e o achado N3 (BL-44):
validadores que não executavam no caminho real de gravação, e entrada acima
dos limites do banco virando 500 em vez de 400. Cada teste referencia o
critério de aceite numerado do plano
docs/planos/DL-008-politica-monetaria-e-validacao-de-escala.md.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.contabilidade.models import (
    Conta,
    ItemLancamento,
    LancamentoContabil,
    NaturezaConta,
    TipoConta,
    TipoPartida,
)
from apps.contabilidade.services import LancamentoInvalido, criar_lancamento
from apps.core.dinheiro import casas_decimais
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
    escritorio = Escritorio.objects.create(nome="Escritório A", cnpj="11111111000111")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa A Ltda", cnpj="11122233000183"
    )
    caixa = Conta.objects.create(
        empresa=empresa,
        codigo="1.1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    capital = Conta.objects.create(
        empresa=empresa,
        codigo="2.1",
        nome="Capital Social",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )
    return {"escritorio": escritorio, "empresa": empresa, "caixa": caixa, "capital": capital}


def _sem_nada_gravado():
    return not LancamentoContabil.objects.exists() and not ItemLancamento.objects.exists()


# ---------------------------------------------------------------------------
# Camada de serviço (apps/contabilidade/services.py)
# ---------------------------------------------------------------------------


# Critério 8: partida com valor negativo -> recusada (LancamentoInvalido),
# nada gravado. Débito/crédito são o campo `tipo`, não o sinal.
def test_partida_negativa_e_rejeitada_pelo_servico(cenario):
    with pytest.raises(LancamentoInvalido):
        criar_lancamento(
            empresa=cenario["empresa"],
            data=date(2024, 1, 1),
            historico="Partida negativa",
            itens=[
                {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("100.00")},
                {
                    "conta": cenario["caixa"],
                    "tipo": TipoPartida.DEBITO,
                    "valor": Decimal("-50.00"),
                },
                {
                    "conta": cenario["capital"],
                    "tipo": TipoPartida.CREDITO,
                    "valor": Decimal("50.00"),
                },
            ],
        )
    assert _sem_nada_gravado()


# Critério 9: partida com valor zero -> recusada, nada gravado.
def test_partida_zero_e_rejeitada_pelo_servico(cenario):
    with pytest.raises(LancamentoInvalido):
        criar_lancamento(
            empresa=cenario["empresa"],
            data=date(2024, 1, 1),
            historico="Partida zero",
            itens=[
                {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("0.00")},
                {
                    "conta": cenario["capital"],
                    "tipo": TipoPartida.CREDITO,
                    "valor": Decimal("0.00"),
                },
            ],
        )
    assert _sem_nada_gravado()


# Critério 10: partida com 3 casas decimais -> recusada, e NÃO arredondada.
# A prova de "não arredondada" é dupla: (a) a exceção é levantada, sem
# devolver um lançamento; (b) nada foi persistido, então o valor não pode
# ter sido silenciosamente ajustado para 2 casas em algum registro.
def test_partida_com_tres_casas_decimais_e_rejeitada_sem_arredondar(cenario):
    with pytest.raises(LancamentoInvalido) as excinfo:
        criar_lancamento(
            empresa=cenario["empresa"],
            data=date(2024, 1, 1),
            historico="Três casas decimais",
            itens=[
                {
                    "conta": cenario["caixa"],
                    "tipo": TipoPartida.DEBITO,
                    "valor": Decimal("100.005"),
                },
                {
                    "conta": cenario["capital"],
                    "tipo": TipoPartida.CREDITO,
                    "valor": Decimal("100.005"),
                },
            ],
        )
    mensagem = str(excinfo.value)
    assert "100.005" in mensagem  # valor recebido
    assert "2" in mensagem  # escala aceita
    assert _sem_nada_gravado()


# Critério 11: o cenário EXATO do achado 4 — 100,004 + 100,004 (débito)
# contra 200,008 (crédito).
#
# Achado 2 da auditoria de 2026-09-12 (erro do arquiteto no enunciado do
# plano, corrigido aqui): a redação original do critério 11 usava crédito
# "200,00", mas 100,004 + 100,004 = 200,008 e NUNCA foi igual a 200,00 — o
# lançamento errado da redação original já era recusado pela checagem
# PRÉ-EXISTENTE de "débitos != créditos", com ou sem esta etapa. Um teste com
# aquele cenário passa por construção, sem exercitar a validação de escala
# que esta etapa introduziu. O auditor provou isso por mutação: substituindo
# a checagem de escala por `if False:`, o teste antigo continuava passando.
#
# O mecanismo REAL do achado 4 exige que a soma dos valores de 3 casas BATA
# exatamente com o total do outro lado, para que a igualdade passasse ANTES
# da correção (100,004 + 100,004 = 200,008 = crédito). É só então que o
# arredondamento do BANCO, ocorrendo DEPOIS da checagem de igualdade,
# reintroduzia o desbalanceamento: 100,004 grava como 100,00 (duas vezes,
# total 200,00) e 200,008 grava como 200,01 — 200,00 de débito contra 200,01
# de crédito, gravado com sucesso, desbalanceado no banco.
def test_achado_4_cem_virgula_zero_zero_quatro_duas_vezes_contra_duzentos_zero_zero_oito(
    cenario,
):
    with pytest.raises(LancamentoInvalido) as excinfo:
        criar_lancamento(
            empresa=cenario["empresa"],
            data=date(2024, 1, 1),
            historico="Achado 4",
            itens=[
                {
                    "conta": cenario["caixa"],
                    "tipo": TipoPartida.DEBITO,
                    "valor": Decimal("100.004"),
                },
                {
                    "conta": cenario["caixa"],
                    "tipo": TipoPartida.DEBITO,
                    "valor": Decimal("100.004"),
                },
                {
                    "conta": cenario["capital"],
                    "tipo": TipoPartida.CREDITO,
                    "valor": Decimal("200.008"),
                },
            ],
        )
    mensagem = str(excinfo.value)
    assert "100.004" in mensagem  # valor recebido do primeiro item recusado
    assert "2" in mensagem  # escala aceita
    assert _sem_nada_gravado()


def test_partida_com_uma_casa_decimal_e_aceita(cenario):
    # Contraprova do critério 10/11: escala <= 2 continua funcionando
    # normalmente (não é uma regressão para "só aceita 2 casas exatas").
    lancamento = criar_lancamento(
        empresa=cenario["empresa"],
        data=date(2024, 1, 1),
        historico="Uma casa decimal",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("100.5")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("100.5")},
        ],
    )
    assert lancamento.itens.count() == 2


# ---------------------------------------------------------------------------
# Limites de entrada na view (apps/contabilidade/views.py) — BL-44 / N3
# ---------------------------------------------------------------------------


def _cliente_autenticado(client, cenario):
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio"], "gestor")
    client.login(username="gestor", password="senha-forte-123")


# Critério 11 (via API): mesmo cenário REAL do achado 4 (ver o comentário
# longo acima do teste equivalente do serviço), mas pela view — prova que a
# validação executa no caminho real da API, não só na chamada direta ao
# serviço.
def test_achado_4_via_api_retorna_400_e_nao_grava_nada(client, cenario):
    _cliente_autenticado(client, cenario)

    response = client.post(
        reverse("contabilidade:lancamentos", args=[cenario["empresa"].id]),
        data={
            "data": "2024-01-01",
            "historico": "Achado 4 via API",
            "itens": [
                {"conta": cenario["caixa"].id, "tipo": "debito", "valor": "100.004"},
                {"conta": cenario["caixa"].id, "tipo": "debito", "valor": "100.004"},
                {"conta": cenario["capital"].id, "tipo": "credito", "valor": "200.008"},
            ],
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert _sem_nada_gravado()


def test_partida_negativa_via_api_retorna_400(client, cenario):
    _cliente_autenticado(client, cenario)

    response = client.post(
        reverse("contabilidade:lancamentos", args=[cenario["empresa"].id]),
        data={
            "data": "2024-01-01",
            "historico": "Partida negativa via API",
            "itens": [
                {"conta": cenario["caixa"].id, "tipo": "debito", "valor": "-100.00"},
                {"conta": cenario["capital"].id, "tipo": "credito", "valor": "-100.00"},
            ],
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert _sem_nada_gravado()


# Critério 12: histórico com 5000 caracteres -> 400, não 500.
def test_historico_acima_do_limite_retorna_400_nao_500(client, cenario):
    _cliente_autenticado(client, cenario)

    response = client.post(
        reverse("contabilidade:lancamentos", args=[cenario["empresa"].id]),
        data={
            "data": "2024-01-01",
            "historico": "x" * 5000,
            "itens": [
                {"conta": cenario["caixa"].id, "tipo": "debito", "valor": "100.00"},
                {"conta": cenario["capital"].id, "tipo": "credito", "valor": "100.00"},
            ],
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert _sem_nada_gravado()


# Não numerado nos 16 critérios, mas apontado em revisão do arquiteto-senior:
# `historico` que não seja string (número, lista, null) chegava até
# `len(historico)` sem checagem de tipo e explodia com `TypeError` não
# capturado -> 500. É a mesma classe de defeito do achado N3 (BL-44):
# entrada do cliente com tipo inesperado virando erro de servidor.
@pytest.mark.parametrize("historico_invalido", [123, ["não", "é", "texto"], None])
def test_historico_com_tipo_invalido_retorna_400_nao_500(client, cenario, historico_invalido):
    _cliente_autenticado(client, cenario)

    response = client.post(
        reverse("contabilidade:lancamentos", args=[cenario["empresa"].id]),
        data={
            "data": "2024-01-01",
            "historico": historico_invalido,
            "itens": [
                {"conta": cenario["caixa"].id, "tipo": "debito", "valor": "100.00"},
                {"conta": cenario["capital"].id, "tipo": "credito", "valor": "100.00"},
            ],
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert _sem_nada_gravado()


# Mesma classe de defeito, para o campo 'data': `date.fromisoformat` exige
# `str` e levanta `TypeError` (não `ValueError`) para outros tipos — sem
# capturar `TypeError` no `except`, um 'data' numérico ou nulo viraria 500.
@pytest.mark.parametrize("data_invalida", [20240101, ["2024-01-01"], None])
def test_data_com_tipo_invalido_retorna_400_nao_500(client, cenario, data_invalida):
    _cliente_autenticado(client, cenario)

    response = client.post(
        reverse("contabilidade:lancamentos", args=[cenario["empresa"].id]),
        data={
            "data": data_invalida,
            "historico": "Data com tipo inválido",
            "itens": [
                {"conta": cenario["caixa"].id, "tipo": "debito", "valor": "100.00"},
                {"conta": cenario["capital"].id, "tipo": "credito", "valor": "100.00"},
            ],
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert _sem_nada_gravado()


# Mesma conferência para 'itens': já estava coberta antes desta etapa
# (`_extrair_itens` recusa qualquer `payload_itens` que não seja lista, e
# cada item que não seja um dict indexável cai no `except (..., TypeError)`
# já existente) — teste de regressão, não correção nova.
@pytest.mark.parametrize("itens_invalidos", [123, "não é uma lista", None, {"conta": 1}])
def test_itens_com_tipo_invalido_retorna_400_nao_500(client, cenario, itens_invalidos):
    _cliente_autenticado(client, cenario)

    response = client.post(
        reverse("contabilidade:lancamentos", args=[cenario["empresa"].id]),
        data={
            "data": "2024-01-01",
            "historico": "Itens com tipo inválido",
            "itens": itens_invalidos,
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert _sem_nada_gravado()


def test_item_individual_com_tipo_invalido_na_lista_retorna_400_nao_500(client, cenario):
    _cliente_autenticado(client, cenario)

    response = client.post(
        reverse("contabilidade:lancamentos", args=[cenario["empresa"].id]),
        data={
            "data": "2024-01-01",
            "historico": "Item da lista não é objeto",
            "itens": ["não é um objeto com conta/tipo/valor", 42],
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert _sem_nada_gravado()


# Critério 13: valor com 25 dígitos -> 400, não 500.
def test_valor_com_vinte_e_cinco_digitos_retorna_400_nao_500(client, cenario):
    _cliente_autenticado(client, cenario)

    valor_25_digitos = "1" * 25  # muito maior que o limite da coluna (max_digits=18)

    response = client.post(
        reverse("contabilidade:lancamentos", args=[cenario["empresa"].id]),
        data={
            "data": "2024-01-01",
            "historico": "Valor gigante",
            "itens": [
                {"conta": cenario["caixa"].id, "tipo": "debito", "valor": valor_25_digitos},
                {"conta": cenario["capital"].id, "tipo": "credito", "valor": valor_25_digitos},
            ],
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert _sem_nada_gravado()


# Critério 14: valor "Infinity" e "NaN" -> 400, não 500.
@pytest.mark.parametrize("valor_nao_finito", ["Infinity", "-Infinity", "NaN"])
def test_valor_nao_finito_retorna_400_nao_500(client, cenario, valor_nao_finito):
    _cliente_autenticado(client, cenario)

    response = client.post(
        reverse("contabilidade:lancamentos", args=[cenario["empresa"].id]),
        data={
            "data": "2024-01-01",
            "historico": "Valor não finito",
            "itens": [
                {"conta": cenario["caixa"].id, "tipo": "debito", "valor": valor_nao_finito},
                {"conta": cenario["capital"].id, "tipo": "credito", "valor": valor_nao_finito},
            ],
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert _sem_nada_gravado()


# Não numerado nos 16 critérios, mas parte do escopo de "limites de entrada"
# da tarefa: data fora da faixa suportada por `datetime.date` (1-9999) já
# cai no 400 existente (`date.fromisoformat` levanta `ValueError`), sem
# precisar de checagem adicional. Teste de regressão para deixar isso
# provado, não apenas presumido.
@pytest.mark.parametrize("data_invalida", ["99999-01-01", "0000-01-01", "10000-06-15"])
def test_data_fora_da_faixa_suportada_retorna_400_nao_500(client, cenario, data_invalida):
    _cliente_autenticado(client, cenario)

    response = client.post(
        reverse("contabilidade:lancamentos", args=[cenario["empresa"].id]),
        data={
            "data": data_invalida,
            "historico": "Data fora de faixa",
            "itens": [
                {"conta": cenario["caixa"].id, "tipo": "debito", "valor": "100.00"},
                {"conta": cenario["capital"].id, "tipo": "credito", "valor": "100.00"},
            ],
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert _sem_nada_gravado()


# ---------------------------------------------------------------------------
# Achados da auditoria de 2026-09-12 (aprovação com ressalvas da DL-008)
# ---------------------------------------------------------------------------


# Achado 1 (MÉDIA, obrigatório): `conta` não numérica dava 500. O `except`
# original só cobria `Conta.DoesNotExist`, `KeyError` e `TypeError`; o
# Postgres levanta `ValueError` ("Field 'id' expected a number but got
# 'abc'") ao tentar resolver um `pk` textual não numérico — mesma classe de
# defeito que esta etapa existe para fechar (entrada do cliente virando
# erro de servidor).
@pytest.mark.parametrize("conta_invalida", ["abc", "", "1x"])
def test_conta_nao_numerica_retorna_400_nao_500(client, cenario, conta_invalida):
    _cliente_autenticado(client, cenario)

    response = client.post(
        reverse("contabilidade:lancamentos", args=[cenario["empresa"].id]),
        data={
            "data": "2024-01-01",
            "historico": "Conta não numérica",
            "itens": [
                {"conta": conta_invalida, "tipo": "debito", "valor": "100.00"},
                {"conta": cenario["capital"].id, "tipo": "credito", "valor": "100.00"},
            ],
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert _sem_nada_gravado()


# Achado 5 (BAIXA, obrigatório): mutação sobrevivente. `if valor <= 0:`
# trocado por `if valor < 0:` continuava passando os testes anteriores,
# porque o critério 9 usa DUAS partidas zero (débito 0 / crédito 0), e o
# TOTAL zero já era recusado pela checagem pré-existente de "total deve ser
# maior que zero" — sem exercitar a checagem de sinal por item. Este cenário
# tem uma partida zero MISTURADA com partidas positivas que, SEM a checagem
# item a item, fechariam a soma perfeitamente (débito 100,00 + crédito
# 100,00): {débito 100,00; débito 0,00; crédito 100,00}.
def test_partida_zero_entre_partidas_positivas_e_rejeitada(cenario):
    with pytest.raises(LancamentoInvalido):
        criar_lancamento(
            empresa=cenario["empresa"],
            data=date(2024, 1, 1),
            historico="Zero entre partidas positivas",
            itens=[
                {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("100.00")},
                {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("0.00")},
                {
                    "conta": cenario["capital"],
                    "tipo": TipoPartida.CREDITO,
                    "valor": Decimal("100.00"),
                },
            ],
        )
    assert _sem_nada_gravado()


# Achado 6 (BAIXA, obrigatório): `criar_lancamento` só era seguro para
# `Decimal` de fato — tipos que o módulo `dinheiro` anuncia e aceita
# (`str`, `int`) quebravam a comparação de sinal com `TypeError` cru, e
# `bool` (subclasse de `int`) passava em silêncio gravando 1,00/0,00.
def test_criar_lancamento_aceita_valor_em_string_normalizando_para_decimal(cenario):
    lancamento = criar_lancamento(
        empresa=cenario["empresa"],
        data=date(2024, 1, 1),
        historico="Valor em string",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": "100.00"},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": "100.00"},
        ],
    )
    item = lancamento.itens.get(conta=cenario["caixa"])
    assert item.valor == Decimal("100.00")
    assert isinstance(item.valor, Decimal)


def test_criar_lancamento_recusa_valor_bool_explicitamente(cenario):
    # `True == 1` e `False == 0` em Python (bool é subclasse de int); sem
    # recusa explícita, `criar_lancamento` gravaria 1,00/0,00 silenciosamente
    # a partir de uma flag verdadeiro/falso — o tipo errado para dinheiro.
    with pytest.raises(LancamentoInvalido) as excinfo:
        criar_lancamento(
            empresa=cenario["empresa"],
            data=date(2024, 1, 1),
            historico="Valor bool",
            itens=[
                {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": True},
                {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": True},
            ],
        )
    assert "bool" in str(excinfo.value).lower()
    assert _sem_nada_gravado()


def test_decimal_0_1_construido_de_float_e_barrado_pela_escala_por_consequencia(cenario):
    """Documenta e prova o limite descrito em `apps.core.dinheiro`: um
    `Decimal` já construído a partir de um `float` PELO CHAMADOR (antes de
    chegar em `criar_lancamento`) não é, e não pode ser, detectado como
    "veio de float" — a informação de origem não sobrevive à construção do
    `Decimal`. `Decimal(0.1)` funciona como defesa em profundidade só porque
    0.1 não é exatamente representável em binário e produz dezenas de casas
    decimais, que a validação de escala já recusa por um motivo totalmente
    diferente (DE-010). Isto NÃO é uma garantia geral: ver o teste seguinte,
    que prova o caso em que ela falha.
    """
    assert casas_decimais(Decimal(0.1)) > 2  # 0.1 em binário não é exato: dezenas de casas
    with pytest.raises(LancamentoInvalido):
        criar_lancamento(
            empresa=cenario["empresa"],
            data=date(2024, 1, 1),
            historico="Decimal de float, escala grande",
            itens=[
                {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal(0.1)},
                {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal(0.1)},
            ],
        )
    assert _sem_nada_gravado()


def test_decimal_de_float_exatamente_representavel_nao_e_detectavel(cenario):
    """Contraprova, documentada de propósito (não é uma falha desta etapa):
    um float EXATAMENTE representável em binário (0.5 = 2^-1) produz um
    `Decimal` com poucas casas ao ser construído, e passa pela validação de
    escala sem ser distinguível de um `Decimal` "limpo". A única defesa real
    é nunca construir `Decimal` a partir de `float` em código novo — é
    exatamente o que `apps.core.dinheiro.para_decimal` torna visível quando
    o `float` chega diretamente (sem já ter sido convertido pelo chamador).
    """
    assert casas_decimais(Decimal(0.5)) == 1
    lancamento = criar_lancamento(
        empresa=cenario["empresa"],
        data=date(2024, 1, 1),
        historico="Decimal de float exato",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal(0.5)},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal(0.5)},
        ],
    )
    assert lancamento.itens.count() == 2


# Achado 7 (BAIXA, obrigatório): parse permissivo do `Decimal` reinterpreta
# entrada — "1_000" (separador de dígitos do Python, PEP 515) grava 1000,00,
# e espaços em volta são aceitos em silêncio. Testado tanto no módulo base
# (`para_decimal`, via `casas_decimais`/`quantizar` em test_dinheiro.py)
# quanto aqui, no caminho real da API.
@pytest.mark.parametrize("valor_reinterpretado", ["1_000", "  100.00  ", "100_00.00"])
def test_valor_com_formato_nao_simples_retorna_400_via_api(client, cenario, valor_reinterpretado):
    _cliente_autenticado(client, cenario)

    response = client.post(
        reverse("contabilidade:lancamentos", args=[cenario["empresa"].id]),
        data={
            "data": "2024-01-01",
            "historico": "Valor com formato não simples",
            "itens": [
                {"conta": cenario["caixa"].id, "tipo": "debito", "valor": valor_reinterpretado},
                {"conta": cenario["capital"].id, "tipo": "credito", "valor": valor_reinterpretado},
            ],
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert _sem_nada_gravado()
