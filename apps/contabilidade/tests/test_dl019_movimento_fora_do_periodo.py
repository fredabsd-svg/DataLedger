"""BL-151 (b) — "há movimento fora do período consultado", e a Conferência
como lugar onde o dado já gravado aparece (achado R6-4b da rodada 6).

**É a razão declarada de a DL-019 existir antes da DL-010.** O auditor mediu,
com um lançamento de 5.000,00 datado `9999-12-31` ao lado de um de 100,00 de
hoje:

    Diário       (período padrão): mostra 5.000,00? False | avisa? False
    Balancete    (período padrão): mostra 5.000,00? False | avisa? False
    Razão        (período padrão): mostra 5.000,00? False | avisa? False
    Conferência:                   mostra 5.000,00? False
    total real de débito na base: 10.200,00

O balancete do período **concilia** — é por isso que nenhuma conferência
aponta. Para achar, o contador precisa suspeitar e alargar o período até o ano
9999. Validar a entrada (RC-77) fecha a porta; estas duas consultas **acendem
a luz** sobre o que já está gravado, que a DL-019 declara explicitamente que
não vai reparar por migração.

Os lançamentos fora da faixa são criados aqui por ORM direto (`objects.
create()`), de propósito: depois do RC-77 o serviço recusa essas datas, e o
dado que este item precisa ENCONTRAR é justamente o que entrou antes da regra
existir (ou por um caminho que não passa por ela).
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
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
from apps.contabilidade.services import (
    criar_lancamento,
    localizar_lancamentos_com_data_fora_da_faixa,
    movimento_fora_do_periodo,
)
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

PERIODO = {"inicio": "2024-01-01", "fim": "2024-01-31"}


@pytest.fixture
def cenario():
    escritorio = Escritorio.objects.create(nome="Escritório BL-151", cnpj="66666666000177")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa BL-151 Ltda", cnpj="66677788000122"
    )
    outra = Empresa.objects.create(
        escritorio=escritorio, razao_social="Outra Empresa BL-151 Ltda", cnpj="77788899000133"
    )
    grupo = Conta.objects.create(
        empresa=empresa,
        codigo="1",
        nome="Ativo",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        aceita_lancamento=False,
    )
    caixa = Conta.objects.create(
        empresa=empresa,
        codigo="1.1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        conta_pai=grupo,
    )
    receita = Conta.objects.create(
        empresa=empresa,
        codigo="2",
        nome="Receita",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )
    usuario = get_user_model().objects.create_user(
        username="gestora-bl151",
        email="gestora-bl151@escritorio.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return {
        "escritorio": escritorio,
        "empresa": empresa,
        "outra_empresa": outra,
        "grupo": grupo,
        "caixa": caixa,
        "receita": receita,
    }


def _lancamento_no_periodo(cenario, data=date(2024, 1, 15), valor="100.00", empresa=None):
    return criar_lancamento(
        empresa=empresa or cenario["empresa"],
        data=data,
        historico="Dentro do período",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal(valor)},
            {"conta": cenario["receita"], "tipo": TipoPartida.CREDITO, "valor": Decimal(valor)},
        ],
    )


def _lancamento_gravado_por_orm(cenario, data, valor="5000.00", empresa=None):
    """Lançamento com data arbitrária, por ORM direto — o caminho que não
    passa por `criar_lancamento` e portanto não é barrado pelo RC-77. É como o
    dado do achado chegou à base, e é o que estas consultas precisam achar."""
    lancamento = LancamentoContabil.objects.create(
        empresa=empresa or cenario["empresa"], data=data, historico=f"Fora da faixa: {data}"
    )
    ItemLancamento.objects.create(
        lancamento=lancamento,
        conta=cenario["caixa"],
        tipo=TipoPartida.DEBITO,
        valor=Decimal(valor),
    )
    ItemLancamento.objects.create(
        lancamento=lancamento,
        conta=cenario["receita"],
        tipo=TipoPartida.CREDITO,
        valor=Decimal(valor),
    )
    return lancamento


# ---------------------------------------------------------------------------
# A consulta de movimento fora do período
# ---------------------------------------------------------------------------


def test_sem_nada_fora_do_periodo_devolve_none(cenario):
    _lancamento_no_periodo(cenario)

    assert (
        movimento_fora_do_periodo(
            empresa=cenario["empresa"], inicio=date(2024, 1, 1), fim=date(2024, 1, 31)
        )
        is None
    )


def test_movimento_posterior_ao_periodo_e_encontrado_com_quantidade_e_data_extrema(cenario):
    _lancamento_no_periodo(cenario)
    _lancamento_gravado_por_orm(cenario, date(9999, 12, 31))
    _lancamento_gravado_por_orm(cenario, date(2030, 5, 4))

    fora = movimento_fora_do_periodo(
        empresa=cenario["empresa"], inicio=date(2024, 1, 1), fim=date(2024, 1, 31)
    )

    assert fora["anteriores"] is None
    assert fora["posteriores"] == {"quantidade": 2, "data_extrema": date(9999, 12, 31)}


def test_movimento_anterior_ao_periodo_usa_a_data_mais_antiga(cenario):
    _lancamento_no_periodo(cenario)
    _lancamento_gravado_por_orm(cenario, date(1, 1, 1))
    _lancamento_gravado_por_orm(cenario, date(2023, 12, 31))

    fora = movimento_fora_do_periodo(
        empresa=cenario["empresa"], inicio=date(2024, 1, 1), fim=date(2024, 1, 31)
    )

    assert fora["posteriores"] is None
    assert fora["anteriores"] == {"quantidade": 2, "data_extrema": date(1, 1, 1)}


def test_bordas_do_periodo_nao_contam_como_fora(cenario):
    """As bordas são as duas INCLUSIVAS em todas as saídas (critério 10 da
    DL-015) — um lançamento exatamente em `inicio` ou em `fim` está DENTRO, e
    avisar que ele está fora seria pior que não avisar nada."""
    _lancamento_no_periodo(cenario, data=date(2024, 1, 1))
    _lancamento_no_periodo(cenario, data=date(2024, 1, 31))

    assert (
        movimento_fora_do_periodo(
            empresa=cenario["empresa"], inicio=date(2024, 1, 1), fim=date(2024, 1, 31)
        )
        is None
    )


def test_movimento_de_outra_empresa_nunca_entra_no_aviso(cenario):
    """Isolamento: o aviso é uma saída como qualquer outra, e um "há movimento
    fora do período" causado por lançamento de OUTRA empresa seria vazamento
    de informação, além de mandar o contador procurar o que não existe."""
    _lancamento_no_periodo(cenario)
    _lancamento_gravado_por_orm(cenario, date(9999, 12, 31), empresa=cenario["outra_empresa"])

    assert (
        movimento_fora_do_periodo(
            empresa=cenario["empresa"], inicio=date(2024, 1, 1), fim=date(2024, 1, 31)
        )
        is None
    )


def test_recorte_por_conta_usa_a_conta_e_as_descendentes(cenario):
    """O Razão consolida a conta consultada com as descendentes
    (`_descendentes_de`, DE-022). O aviso precisa usar o MESMO conjunto, ou
    diria "não há movimento fora" para um grupo cujo filho tem movimento
    fora."""
    _lancamento_no_periodo(cenario)
    _lancamento_gravado_por_orm(cenario, date(9999, 12, 31))

    pelo_grupo = movimento_fora_do_periodo(
        empresa=cenario["empresa"],
        inicio=date(2024, 1, 1),
        fim=date(2024, 1, 31),
        conta=cenario["grupo"],
    )
    pela_folha = movimento_fora_do_periodo(
        empresa=cenario["empresa"],
        inicio=date(2024, 1, 1),
        fim=date(2024, 1, 31),
        conta=cenario["caixa"],
    )

    # O movimento está em `1.1 Caixa`, descendente de `1 Ativo`: os dois
    # recortes precisam enxergá-lo.
    assert pelo_grupo["posteriores"]["quantidade"] == 1
    assert pela_folha["posteriores"]["quantidade"] == 1


def test_recorte_por_conta_ignora_conta_sem_movimento_fora(cenario):
    _lancamento_no_periodo(cenario)
    _lancamento_gravado_por_orm(cenario, date(9999, 12, 31))

    # A conta `2 Receita` TEM movimento fora (o par do lançamento por ORM),
    # então para provar o recorte usamos uma conta nova, sem item nenhum.
    isolada = Conta.objects.create(
        empresa=cenario["empresa"],
        codigo="3",
        nome="Conta sem movimento",
        tipo=TipoConta.DESPESA,
        natureza=NaturezaConta.DEVEDORA,
    )

    assert (
        movimento_fora_do_periodo(
            empresa=cenario["empresa"],
            inicio=date(2024, 1, 1),
            fim=date(2024, 1, 31),
            conta=isolada,
        )
        is None
    )


def test_contagem_por_conta_conta_lancamentos_e_nao_partidas(cenario):
    """Um lançamento com débito E crédito na mesma subárvore tem dois itens.
    Sem `distinct=True` a contagem diria "2 lançamentos" onde há um, e o aviso
    mentiria sobre quanto há para procurar."""
    _lancamento_no_periodo(cenario)
    lancamento = LancamentoContabil.objects.create(
        empresa=cenario["empresa"], data=date(9999, 12, 31), historico="dois itens na subárvore"
    )
    ItemLancamento.objects.create(
        lancamento=lancamento,
        conta=cenario["caixa"],
        tipo=TipoPartida.DEBITO,
        valor=Decimal("10.00"),
    )
    ItemLancamento.objects.create(
        lancamento=lancamento,
        conta=cenario["caixa"],
        tipo=TipoPartida.CREDITO,
        valor=Decimal("10.00"),
    )

    fora = movimento_fora_do_periodo(
        empresa=cenario["empresa"],
        inicio=date(2024, 1, 1),
        fim=date(2024, 1, 31),
        conta=cenario["caixa"],
    )

    assert fora["posteriores"]["quantidade"] == 1


# ---------------------------------------------------------------------------
# A API das três saídas com período
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rota", ["diario", "balancete"])
def test_api_avisa_movimento_fora_do_periodo(client, cenario, rota):
    """O fato invisível era invisível pela API também (item 2 da DE-034):
    fechar só na tela repetiria o vício que o R6-2 nomeou."""
    assert client.login(username="gestora-bl151", password="senha-forte-123")
    _lancamento_no_periodo(cenario)
    _lancamento_gravado_por_orm(cenario, date(9999, 12, 31))

    corpo = client.get(
        reverse(f"contabilidade:{rota}", args=[cenario["empresa"].id]), PERIODO
    ).json()

    aviso = corpo["movimento_fora_do_periodo"]
    assert aviso is not None, corpo
    assert aviso["posteriores"] == {"quantidade": 1, "data_extrema": "9999-12-31"}


def test_api_do_razao_avisa_pela_conta_consultada(client, cenario):
    assert client.login(username="gestora-bl151", password="senha-forte-123")
    _lancamento_no_periodo(cenario)
    _lancamento_gravado_por_orm(cenario, date(9999, 12, 31))

    corpo = client.get(
        reverse("contabilidade:razao", args=[cenario["empresa"].id, cenario["caixa"].id]), PERIODO
    ).json()

    assert corpo["movimento_fora_do_periodo"]["posteriores"]["data_extrema"] == "9999-12-31"


@pytest.mark.parametrize("rota", ["diario", "balancete"])
def test_api_declara_a_chave_mesmo_quando_nao_ha_nada_fora(client, cenario, rota):
    """A chave existe SEMPRE, com `null`: um cliente que só a veja quando há
    movimento não distingue "não há" de "esta versão do servidor não responde
    isso"."""
    assert client.login(username="gestora-bl151", password="senha-forte-123")
    _lancamento_no_periodo(cenario)

    corpo = client.get(
        reverse(f"contabilidade:{rota}", args=[cenario["empresa"].id]), PERIODO
    ).json()

    assert "movimento_fora_do_periodo" in corpo
    assert corpo["movimento_fora_do_periodo"] is None


def test_totais_do_periodo_continuam_conciliando_com_o_aviso_presente(client, cenario):
    """O aviso NÃO muda os números do período — ele diz que existe mais. Se o
    valor de fora entrasse no total, o balancete deixaria de conciliar com o
    Diário do mesmo recorte, e a cura seria pior que a doença."""
    assert client.login(username="gestora-bl151", password="senha-forte-123")
    _lancamento_no_periodo(cenario, valor="100.00")
    _lancamento_gravado_por_orm(cenario, date(9999, 12, 31), valor="5000.00")

    diario = client.get(
        reverse("contabilidade:diario", args=[cenario["empresa"].id]), PERIODO
    ).json()

    assert diario["total_debito"] == "100.00"
    assert diario["total_credito"] == "100.00"
    assert diario["movimento_fora_do_periodo"] is not None


# ---------------------------------------------------------------------------
# A Conferência (sem período): o que está fora da faixa plausível
# ---------------------------------------------------------------------------


def test_conferencia_localiza_lancamento_fora_da_faixa(cenario):
    dentro = _lancamento_no_periodo(cenario)
    fora_para_frente = _lancamento_gravado_por_orm(cenario, date(9999, 12, 31))
    fora_para_tras = _lancamento_gravado_por_orm(cenario, date(1999, 12, 31))

    encontrados = localizar_lancamentos_com_data_fora_da_faixa(empresa=cenario["empresa"])

    ids = [lancamento.pk for lancamento in encontrados]
    assert ids == [fora_para_tras.pk, fora_para_frente.pk]  # ordenado por data
    assert dentro.pk not in ids


def test_conferencia_em_base_sadia_nao_aponta_nada(cenario):
    _lancamento_no_periodo(cenario)
    _lancamento_no_periodo(cenario, data=timezone.localdate() + timedelta(days=30))

    assert localizar_lancamentos_com_data_fora_da_faixa(empresa=cenario["empresa"]) == []


def test_conferencia_nao_mistura_empresas(cenario):
    _lancamento_gravado_por_orm(cenario, date(9999, 12, 31), empresa=cenario["outra_empresa"])

    assert localizar_lancamentos_com_data_fora_da_faixa(empresa=cenario["empresa"]) == []


def test_api_da_conferencia_expoe_a_categoria_nova(client, cenario):
    """É a única saída em que o `9999-12-31` já gravado aparece sem o contador
    precisar suspeitar primeiro."""
    assert client.login(username="gestora-bl151", password="senha-forte-123")
    fora = _lancamento_gravado_por_orm(cenario, date(9999, 12, 31))

    corpo = client.get(
        reverse("contabilidade:conferencia-lotes-desbalanceados", args=[cenario["empresa"].id])
    ).json()

    assert corpo["lancamentos_com_data_fora_da_faixa"] == [
        {"id": fora.pk, "data": "9999-12-31", "historico": fora.historico}
    ]
