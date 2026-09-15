"""BL-165 — o Razão percorre a subárvore de contas UMA vez, não duas.

## O defeito que este arquivo trava

A DL-019 acrescentou ao Razão o aviso "há movimento fora do período"
(BL-151). O aviso precisa do MESMO recorte de contas que a apuração usa (a
conta e todas as descendentes), e `_descendentes_de` busca esse conjunto
**uma consulta por NÍVEL de profundidade** do plano. As duas superfícies do
Razão — a tela e a API — pediram o recorte passando a `Conta`, então a
subárvore foi percorrida **duas vezes por requisição**: uma na apuração,
outra no aviso.

O teto de consultas do Razão, declarado em função da profundidade desde a
DL-015 (`test_dl015_saidas_com_periodo.py`, achado novo 5), reprovou: num
plano de profundidade 8 mediu **24** consultas onde o teto é 17.

## Por que este arquivo existe, e não apenas a correção

O autor de `movimento_fora_do_periodo` **previu este defeito por escrito**. A
docstring da função dizia, e ainda diz, que `ids_contas` "vem no resultado
[de `apurar_razao`], na chave `ids_contas`". `apurar_razao` **não devolvia
essa chave**. A frase era falsa, e porque o caminho barato que ela anunciava
não existia, as duas superfícies chamaram o caro — é a nona ocorrência da
família "comentário que afirma mais do que a defesa entrega" no projeto, e a
segunda em que o comentário **causou** o defeito (a primeira foi a
BL-142/BL-146, DE-034).

Daí a forma dos testes daqui: cada metade da promessa da docstring tem um
teste que consegue falhar.

1. A chave existe e é o conjunto que foi somado (`test_apurar_razao_*`).
2. Nenhuma das duas superfícies percorre a subárvore duas vezes — medido
   contando as chamadas reais a `_descendentes_de`, não lendo o fonte.
3. O teto de consultas não cresce mais de UMA por nível de profundidade,
   medido em duas profundidades e comparado — a forma que acusa a travessia
   dobrada sem depender do custo fixo de middleware/permissão.
4. A apresentação do aviso não regrediu ao trocar o parâmetro de consulta: o
   aviso do Razão continua falando da CONTA (não da empresa) e continua
   recortando pela subárvore.

Dados 100% sintéticos, criados nos próprios testes.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.contabilidade import services
from apps.contabilidade.models import (
    Conta,
    ItemLancamento,
    LancamentoContabil,
    NaturezaConta,
    TipoConta,
    TipoPartida,
)
from apps.contabilidade.services import apurar_razao, criar_lancamento
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

PERIODO = {"inicio": "2024-01-01", "fim": "2024-01-31"}
INICIO = date(2024, 1, 1)
FIM = date(2024, 1, 31)
SENHA = "senha-forte-123"


@pytest.fixture
def cenario():
    """Plano com um grupo, uma folha subordinada a ele e uma conta IRMÃ fora
    da subárvore (a irmã é o que prova que o recorte do aviso é a subárvore,
    e não a empresa inteira).

    1   Ativo            (grupo)
      1.1 Caixa          (folha, subordinada ao grupo)
    2   Capital Social   (fora da subárvore de "1")
    """
    escritorio = Escritorio.objects.create(nome="Escritório BL-165", cnpj="88888888000188")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa BL-165 Ltda", cnpj="88899900000111"
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
    capital = Conta.objects.create(
        empresa=empresa,
        codigo="2",
        nome="Capital Social",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )
    usuario = get_user_model().objects.create_user(
        username="gestora-bl165", email="gestora-bl165@escritorio.com.br", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return {
        "escritorio": escritorio,
        "empresa": empresa,
        "grupo": grupo,
        "caixa": caixa,
        "capital": capital,
        "usuario": usuario,
    }


def _autenticar(client):
    assert client.login(username="gestora-bl165", password=SENHA)


def _lancamento_no_periodo(cenario, valor="100.00"):
    return criar_lancamento(
        empresa=cenario["empresa"],
        data=date(2024, 1, 15),
        historico="Dentro do período",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal(valor)},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal(valor)},
        ],
    )


def _lancamento_fora_do_periodo_por_orm(cenario, *, conta_debito, conta_credito, data):
    """Lançamento com data fora do período gravado por ORM direto — é o caminho
    que não passa por `criar_lancamento` e portanto não é barrado pela faixa do
    RC-77, e é como o dado do achado R6-4b chegou à base real."""
    lancamento = LancamentoContabil.objects.create(
        empresa=cenario["empresa"], data=data, historico=f"Fora do período: {data}"
    )
    for conta, tipo in ((conta_debito, TipoPartida.DEBITO), (conta_credito, TipoPartida.CREDITO)):
        ItemLancamento.objects.create(
            lancamento=lancamento, conta=conta, tipo=tipo, valor=Decimal("5000.00")
        )
    return lancamento


def _corrente_de_contas(empresa, profundidade, prefixo):
    """Cria uma corrente de `profundidade` contas, cada uma filha da anterior, e
    devolve a RAIZ — o caso em que `_descendentes_de` paga uma consulta por
    nível. `objects.create()` não chama `full_clean()`, o mesmo atalho que o
    teste de teto da DL-015 usa para montar o plano profundo.

    `prefixo` separa os códigos de duas correntes na MESMA empresa (o
    `codigo_unico_por_empresa` as recusaria juntas) — as duas precisam
    coexistir para a medição comparar profundidades sem trocar de base.
    """
    raiz = None
    conta_pai = None
    for nivel in range(profundidade):
        conta_pai = Conta.objects.create(
            empresa=empresa,
            codigo=f"{prefixo}.{nivel}",
            nome=f"Nível {nivel} da corrente {prefixo}",
            tipo=TipoConta.ATIVO,
            natureza=NaturezaConta.DEVEDORA,
            conta_pai=conta_pai,
        )
        if raiz is None:
            raiz = conta_pai
    return raiz


@pytest.fixture
def contador_de_travessias(monkeypatch):
    """Conta as chamadas REAIS a `_descendentes_de` (a função que custa uma
    consulta por nível), preservando o comportamento.

    Medir a chamada, e não o fonte, é deliberado: a BL-146 mostrou que
    verificar uma promessa de comentário procurando um nome no texto do módulo
    produz um teste que não consegue falhar, porque o nome sobrevive no próprio
    comentário.
    """
    original = services._descendentes_de
    chamadas = []

    def espiao(conta, empresa):
        chamadas.append(conta.pk)
        return original(conta, empresa)

    monkeypatch.setattr(services, "_descendentes_de", espiao)
    return chamadas


# ---------------------------------------------------------------------------
# 1. A promessa da docstring: a chave existe e é o conjunto que foi somado
# ---------------------------------------------------------------------------


def test_apurar_razao_devolve_o_conjunto_de_contas_que_somou(cenario):
    """A frase da docstring de `movimento_fora_do_periodo` — "ele vem no
    resultado, na chave `ids_contas`" — era falsa, e a falsidade dela causou a
    regressão. Este é o teste que a torna conferível."""
    _lancamento_no_periodo(cenario)

    apuracao = apurar_razao(
        conta=cenario["grupo"], empresa=cenario["empresa"], inicio=INICIO, fim=FIM
    )

    assert "ids_contas" in apuracao, sorted(apuracao)
    # O conjunto EXATO que a apuração somou: o grupo e a folha subordinada,
    # nunca a conta irmã "2 Capital Social".
    assert set(apuracao["ids_contas"]) == {cenario["grupo"].pk, cenario["caixa"].pk}
    assert cenario["capital"].pk not in apuracao["ids_contas"]


def test_ids_contas_de_conta_folha_e_so_ela_mesma(cenario):
    apuracao = apurar_razao(
        conta=cenario["caixa"], empresa=cenario["empresa"], inicio=INICIO, fim=FIM
    )

    assert set(apuracao["ids_contas"]) == {cenario["caixa"].pk}
    assert apuracao["consolidado"] is False


def test_ids_contas_e_imutavel(cenario):
    """É um fato já apurado: quem recebe o resultado não pode alterar o
    conjunto que a apuração declara ter somado — do contrário o aviso poderia
    consultar um recorte diferente do que a tela mostra, e os dois deixariam de
    conciliar sem nada acusar."""
    apuracao = apurar_razao(
        conta=cenario["grupo"], empresa=cenario["empresa"], inicio=INICIO, fim=FIM
    )

    assert isinstance(apuracao["ids_contas"], frozenset)
    with pytest.raises(AttributeError):
        apuracao["ids_contas"].add(cenario["capital"].pk)


# ---------------------------------------------------------------------------
# 2. Nenhuma das duas superfícies percorre a subárvore duas vezes
# ---------------------------------------------------------------------------


def test_tela_do_razao_percorre_a_subarvore_uma_unica_vez(client, cenario, contador_de_travessias):
    _autenticar(client)
    _lancamento_no_periodo(cenario)
    _lancamento_fora_do_periodo_por_orm(
        cenario,
        conta_debito=cenario["caixa"],
        conta_credito=cenario["capital"],
        data=date(9999, 12, 31),
    )

    resposta = client.get(
        reverse("contabilidade_web:razao", args=[cenario["empresa"].pk, cenario["grupo"].pk]),
        PERIODO,
    )

    assert resposta.status_code == 200
    # O aviso de fato apareceu — sem isto o teste passaria trivialmente num
    # servidor que simplesmente não consulta nada.
    assert resposta.context["movimento_fora_do_periodo"] is not None
    assert contador_de_travessias == [cenario["grupo"].pk], contador_de_travessias


def test_api_do_razao_percorre_a_subarvore_uma_unica_vez(client, cenario, contador_de_travessias):
    _autenticar(client)
    _lancamento_no_periodo(cenario)
    _lancamento_fora_do_periodo_por_orm(
        cenario,
        conta_debito=cenario["caixa"],
        conta_credito=cenario["capital"],
        data=date(9999, 12, 31),
    )

    corpo = client.get(
        reverse("contabilidade:razao", args=[cenario["empresa"].pk, cenario["grupo"].pk]),
        PERIODO,
    ).json()

    assert corpo["movimento_fora_do_periodo"] is not None, corpo
    assert contador_de_travessias == [cenario["grupo"].pk], contador_de_travessias


# ---------------------------------------------------------------------------
# 3. O teto de consultas cresce UMA por nível, não duas
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rota", ["contabilidade_web:razao", "contabilidade:razao"], ids=["tela", "api"]
)
def test_consultas_do_razao_crescem_uma_por_nivel_de_profundidade(client, cenario, rota):
    """A forma que acusa a travessia dobrada sem depender do custo fixo de
    middleware, sessão e permissão: medir DUAS profundidades e comparar a
    diferença com a diferença de níveis.

    `_descendentes_de` paga uma consulta por nível, então oito níveis a mais
    valem no máximo oito consultas a mais. Com a subárvore percorrida duas
    vezes valem dezesseis — foi assim que o Razão de um plano de profundidade
    8 passou de 16 para 24 consultas e estourou o teto da DL-015.

    Este teste NÃO substitui
    `test_razao_numero_de_consultas_do_grupo_raiz_de_plano_profundo`
    (`test_dl015_saidas_com_periodo.py`), que declara o teto absoluto: ele
    cobre a outra metade, a taxa de crescimento, e cobre também a API, que o
    teste da DL-015 não alcança.
    """
    _autenticar(client)
    _lancamento_no_periodo(cenario)
    rasa = _corrente_de_contas(cenario["empresa"], 4, prefixo="8")
    profunda = _corrente_de_contas(cenario["empresa"], 12, prefixo="9")

    def consultas_do_razao(conta):
        endereco = reverse(rota, args=[cenario["empresa"].pk, conta.pk])
        client.get(endereco, PERIODO)  # aquecimento: conexão, sessão, migrações
        with CaptureQueriesContext(connection) as capturadas:
            resposta = client.get(endereco, PERIODO)
        assert resposta.status_code == 200
        return len(capturadas)

    consultas_rasa = consultas_do_razao(rasa)
    consultas_profunda = consultas_do_razao(profunda)

    niveis_a_mais = 12 - 4
    assert consultas_profunda - consultas_rasa <= niveis_a_mais, (
        f"{consultas_rasa} consultas em profundidade 4 e {consultas_profunda} em 12: "
        f"{consultas_profunda - consultas_rasa} a mais para {niveis_a_mais} níveis a mais. "
        "Mais de uma consulta por nível significa que a subárvore está sendo "
        "percorrida mais de uma vez na mesma requisição (BL-165)."
    )
    # Teto absoluto, na mesma forma da DL-015 (profundidade + 9), para a
    # comparação acima não passar num servidor que ficou caro nas DUAS medidas.
    assert consultas_profunda <= 12 + 9, consultas_profunda


# ---------------------------------------------------------------------------
# 4. A apresentação e o recorte do aviso não regrediram
# ---------------------------------------------------------------------------


def test_aviso_do_razao_continua_recortando_pela_subarvore_e_nao_pela_empresa(client, cenario):
    """Trocar o parâmetro de consulta de `conta` para `ids_contas` não pode
    alargar o recorte para a empresa: o Razão de uma conta SEM movimento fora
    do período não avisa, mesmo havendo movimento fora em outra conta da mesma
    empresa."""
    _autenticar(client)
    _lancamento_no_periodo(cenario)
    isolada = Conta.objects.create(
        empresa=cenario["empresa"],
        codigo="3",
        nome="Conta sem movimento nenhum",
        tipo=TipoConta.DESPESA,
        natureza=NaturezaConta.DEVEDORA,
    )
    # O movimento fora do período está em "1.1 Caixa" e "2 Capital Social" —
    # nenhuma das duas é a conta consultada nem descendente dela.
    _lancamento_fora_do_periodo_por_orm(
        cenario,
        conta_debito=cenario["caixa"],
        conta_credito=cenario["capital"],
        data=date(9999, 12, 31),
    )

    resposta = client.get(
        reverse("contabilidade_web:razao", args=[cenario["empresa"].pk, isolada.pk]), PERIODO
    )
    corpo_api = client.get(
        reverse("contabilidade:razao", args=[cenario["empresa"].pk, isolada.pk]), PERIODO
    ).json()

    assert resposta.context["movimento_fora_do_periodo"] is None
    assert corpo_api["movimento_fora_do_periodo"] is None


def test_aviso_do_razao_enxerga_movimento_fora_do_periodo_de_conta_DESCENDENTE(client, cenario):
    """A outra ponta do mesmo recorte: o grupo precisa ver o que está fora do
    período na FILHA. É o que se perderia se `ids_contas` chegasse vazio ou só
    com a conta consultada."""
    _autenticar(client)
    _lancamento_no_periodo(cenario)
    _lancamento_fora_do_periodo_por_orm(
        cenario,
        conta_debito=cenario["caixa"],
        conta_credito=cenario["capital"],
        data=date(9999, 12, 31),
    )

    resposta = client.get(
        reverse("contabilidade_web:razao", args=[cenario["empresa"].pk, cenario["grupo"].pk]),
        PERIODO,
    )
    corpo_api = client.get(
        reverse("contabilidade:razao", args=[cenario["empresa"].pk, cenario["grupo"].pk]),
        PERIODO,
    ).json()

    aviso = resposta.context["movimento_fora_do_periodo"]
    assert aviso["posteriores"] == {"quantidade": 1, "data_extrema": date(9999, 12, 31)}
    assert corpo_api["movimento_fora_do_periodo"]["posteriores"] == {
        "quantidade": 1,
        "data_extrema": "9999-12-31",
    }


def test_aviso_do_razao_na_tela_continua_falando_da_CONTA_e_nao_da_empresa(client, cenario):
    """`conta` deixou de ser o parâmetro de CONSULTA do aviso, mas continua
    sendo o de APRESENTAÇÃO: é a chave `"conta"` do contexto que faz o parcial
    dizer "esta conta (incluindo as subordinadas)" em vez de "esta empresa".
    Perder isso ao trocar o parâmetro seria trocar um defeito de desempenho por
    um de texto."""
    _autenticar(client)
    _lancamento_no_periodo(cenario)
    _lancamento_fora_do_periodo_por_orm(
        cenario,
        conta_debito=cenario["caixa"],
        conta_credito=cenario["capital"],
        data=date(9999, 12, 31),
    )

    resposta = client.get(
        reverse("contabilidade_web:razao", args=[cenario["empresa"].pk, cenario["grupo"].pk]),
        PERIODO,
    )

    assert resposta.context["movimento_fora_do_periodo"]["conta"] == cenario["grupo"]
    html = resposta.content.decode()
    assert "esta conta (incluindo as subordinadas) tem movimento" in html
    assert "esta empresa tem movimento" not in html


def test_aviso_do_razao_na_tela_mantem_o_link_que_ALARGA_o_periodo(client, cenario):
    """O caminho de correção: o link amplia o período até alcançar o que está
    fora, sem abandonar o que o contador já estava vendo."""
    _autenticar(client)
    _lancamento_no_periodo(cenario)
    _lancamento_fora_do_periodo_por_orm(
        cenario,
        conta_debito=cenario["caixa"],
        conta_credito=cenario["capital"],
        data=date(9999, 12, 31),
    )

    endereco = reverse("contabilidade_web:razao", args=[cenario["empresa"].pk, cenario["grupo"].pk])
    resposta = client.get(endereco, PERIODO)

    aviso = resposta.context["movimento_fora_do_periodo"]
    assert aviso["inicio_ampliado"] == INICIO  # alarga, não substitui
    assert aviso["fim_ampliado"] == date(9999, 12, 31)
    assert aviso["url_ampliada"].startswith(endereco)
    assert "inicio=2024-01-01" in aviso["url_ampliada"]
    assert "fim=9999-12-31" in aviso["url_ampliada"]


# ---------------------------------------------------------------------------
# 5. O plano inconsistente continua respondendo 409, não 500
# ---------------------------------------------------------------------------


def test_razao_de_hierarquia_com_ciclo_continua_respondendo_409_nas_duas_superficies(
    client, cenario
):
    """A correção tirou a chamada do aviso de dentro do `try` da tela, porque
    ela já não percorre a hierarquia e já não pode levantar
    `HierarquiaInconsistente`. O que não pode mudar é a RESPOSTA a um plano com
    ciclo: 409 nomeando a conta, nunca um 500 mudo.

    O ciclo é criado por `objects.update()` (contornando `Conta.clean()`, que o
    recusa no caminho validado) — a mesma via da auditoria.
    """
    _autenticar(client)
    # "1 Ativo" passa a ser filha da própria filha: ciclo alcançável a partir
    # das duas contas.
    Conta.objects.filter(pk=cenario["grupo"].pk).update(conta_pai_id=cenario["caixa"].pk)

    resposta_tela = client.get(
        reverse("contabilidade_web:razao", args=[cenario["empresa"].pk, cenario["grupo"].pk]),
        PERIODO,
    )
    resposta_api = client.get(
        reverse("contabilidade:razao", args=[cenario["empresa"].pk, cenario["grupo"].pk]),
        PERIODO,
    )

    assert resposta_tela.status_code == 409
    assert resposta_api.status_code == 409
    assert "Ciclo" in resposta_api.json()["detail"]
    assert cenario["grupo"].codigo in resposta_api.json()["detail"]
