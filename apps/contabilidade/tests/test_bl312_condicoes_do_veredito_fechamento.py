"""BL-312 (M3 da auditoria DL-024 rodada 3,
docs/auditorias/2026-09-18-dl-024-rodada-3.md): `_veredito_fechamento`
declara, no próprio docstring, um conjunto de condições que precisam ser
TODAS verdadeiras para o rodapé dizer "Fecha". O auditor mediu que uma
delas — `linhas_excluidas_do_total == 0` — podia ser REMOVIDA do código sem
derrubar nenhum teste (`1451 passed`): nenhum caso em toda a suíte isolava
essa condição como a ÚNICA que decide.

**Requisito geral desta etapa** (instrução do `arquiteto-senior` na rodada
5): cada condição que o veredito declara exigir tem de ter um caso em que
ela — e só ela — decide o resultado. "Isolar" significa: um estado em que
TODAS as outras condições estão no valor que permite "Fecha", e SÓ a
condição em questão está no valor que impede — a mutação que troca essa
condição por uma sempre-verdadeira tem de derrubar o teste.

Este arquivo faz o levantamento completo — as quatro condições que a
`_veredito_fechamento` já tinha, MAIS a quinta que o BL-307 acrescentou
nesta mesma rodada (`bloqueado_por_outro_erro`) — e registra, para cada
uma, se ela É isolável e qual caso isola, ou, com a mesma honestidade que
o auditor usou para o mutante `>=1` (achado M3: "não conto como achado:
é mutante equivalente"), por que ela NÃO é isolável sozinha.

As cinco condições de `"fecha"`, lidas de `views_web._veredito_fechamento`:

1. `debito == credito`
2. `debito > 0`
3. `linhas_excluidas_do_total == 0`
4. `num_partidas_validas >= 2`
5. `not bloqueado_por_outro_erro` (BL-307, rodada 5 — histórico, chave de
   idempotência ou data inválidos, sem relação com débito/crédito/linha)

Dados 100% sintéticos, criados nos próprios testes.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.contabilidade.models import Conta, LancamentoContabil, NaturezaConta, TipoConta
from apps.contabilidade.views import TAMANHO_MAXIMO_HISTORICO
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def cen():
    escritorio = Escritorio.objects.create(nome="Escritório BL-312", cnpj="44433322000166")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa BL-312 Ltda", cnpj="44455566000133"
    )
    caixa = Conta.objects.create(
        empresa=empresa,
        codigo="1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    receita = Conta.objects.create(
        empresa=empresa,
        codigo="2",
        nome="Receita",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )
    usuario = get_user_model().objects.create_user(
        username="gestora-bl312",
        email="gestora-bl312@escritorio.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return {"escritorio": escritorio, "empresa": empresa, "caixa": caixa, "receita": receita}


def _url_tela(cen):
    return reverse("contabilidade_web:lancamento_novo", args=[cen["empresa"].id])


def _login(client):
    assert client.login(username="gestora-bl312", password="senha-forte-123")


def _duas_linhas(cen, *, valor_debito, valor_credito, acao, chave, historico="BL-312"):
    return {
        "acao": acao,
        "num_linhas": "2",
        "data": timezone.localdate().isoformat(),
        "historico": historico,
        "chave_idempotencia": chave,
        "conta_1": str(cen["caixa"].id),
        "tipo_1": "debito",
        "valor_1": valor_debito,
        "conta_2": str(cen["receita"].id),
        "tipo_2": "credito",
        "valor_2": valor_credito,
    }


# ---------------------------------------------------------------------------
# Controle: o estado em que as CINCO condições valem — referência para cada
# teste de isolamento comparar contra.
# ---------------------------------------------------------------------------


def test_controle_as_cinco_condicoes_juntas_e_fecha(client, cen):
    _login(client)
    resposta = client.post(
        _url_tela(cen),
        _duas_linhas(
            cen,
            valor_debito="500,00",
            valor_credito="500,00",
            acao="adicionar_linha",
            chave="k-bl312-controle",
        ),
    )
    assert resposta.status_code == 200
    assert resposta.context["veredito_fechamento"] == "fecha"


# ---------------------------------------------------------------------------
# Condição 1 — debito == credito
# ---------------------------------------------------------------------------


def test_condicao1_debito_igual_credito_e_a_unica_que_decide(client, cen):
    """Isolada: débito e crédito positivos e DIFERENTES; nenhuma linha
    excluída (condição 3 ok); duas partidas válidas (condição 4 ok);
    histórico e data válidos (condição 5 ok). Só a condição 1 falha —
    resultado tem de ser `"nao_fecha"`, nunca `"fecha"` nem
    `"nao_conferido"` (a diferença é REAL, a tela precisa dizer de
    quanto)."""
    _login(client)
    resposta = client.post(
        _url_tela(cen),
        _duas_linhas(
            cen,
            valor_debito="500,00",
            valor_credito="300,00",
            acao="adicionar_linha",
            chave="k-bl312-c1",
        ),
    )
    assert resposta.status_code == 200
    assert resposta.context["veredito_fechamento"] == "nao_fecha"
    assert resposta.context["diferenca_fechamento_ptbr"] == "200,00"


# ---------------------------------------------------------------------------
# Condição 2 — debito > 0
# ---------------------------------------------------------------------------


def test_condicao2_debito_maior_que_zero_e_a_unica_que_decide(client, cen):
    """Isolada: débito == crédito == 0,00 (condição 1 continua valendo —
    são IGUAIS); nenhuma linha excluída; duas partidas válidas; histórico e
    data válidos. Só a condição 2 falha — resultado `"nao_conferido"`
    (nunca "nao_fecha", porque os dois lados SÃO iguais; nunca "fecha",
    porque zero não é um total conferido)."""
    _login(client)
    resposta = client.post(
        _url_tela(cen),
        _duas_linhas(
            cen,
            valor_debito="0,00",
            valor_credito="0,00",
            acao="adicionar_linha",
            chave="k-bl312-c2",
        ),
    )
    assert resposta.status_code == 200
    assert resposta.context["veredito_fechamento"] == "nao_conferido"


# ---------------------------------------------------------------------------
# Condição 3 — linhas_excluidas_do_total == 0 (o BURACO que o M3 mediu:
# nenhum teste da suíte isolava esta condição antes desta etapa)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("acao", ["adicionar_linha", "gravar"])
def test_condicao3_linhas_excluidas_e_a_unica_que_decide(client, cen, acao):
    """Isolada — o caso que faltava: DUAS partidas válidas BATENDO
    (condições 1, 2 e 4 valem) MAIS uma terceira linha descartada (valor
    "abc"), histórico e data válidos (condição 5 ok). Só a condição 3
    falha — resultado `"nao_conferido"`, nos DOIS valores de `acao` (a
    recomendação explícita do auditor: o mesmo buraco existia nos dois
    caminhos, e a correção do BL-307 cobre o `gravar` que faltava)."""
    _login(client)
    corpo = _duas_linhas(
        cen,
        valor_debito="500,00",
        valor_credito="500,00",
        acao=acao,
        chave=f"k-bl312-c3-{acao}",
    )
    corpo["num_linhas"] = "3"
    corpo["conta_3"] = str(cen["caixa"].id)
    corpo["tipo_3"] = "debito"
    corpo["valor_3"] = "abc"

    resposta = client.post(_url_tela(cen), corpo)

    status_esperado = 200 if acao == "adicionar_linha" else 400
    assert resposta.status_code == status_esperado
    assert resposta.context["linhas_excluidas_do_total"] == 1
    assert resposta.context["veredito_fechamento"] == "nao_conferido"
    if acao == "gravar":
        assert (
            LancamentoContabil.objects.filter(chave_idempotencia=f"k-bl312-c3-{acao}").count() == 0
        )


# ---------------------------------------------------------------------------
# Condição 4 — num_partidas_validas >= 2
#
# Registro de honestidade, no mesmo padrão do M3 do auditor: esta condição
# NÃO é isolável por um mutante que a AFROUXE (`>= 2` -> `>= 1` ou `>= 0`).
# Prova, por construção: para `debito == credito` E `debito > 0` valerem ao
# mesmo tempo, é PRECISO existir pelo menos um item de cada tipo (débito e
# crédito) contribuindo um valor positivo — cada item contribui só para UM
# dos dois acumuladores (nunca os dois), então com 0 ou 1 item válido pelo
# menos um dos dois acumuladores fica em zero, o que já reprova a condição
# 2 sozinha. Ou seja: sempre que as condições 1 e 2 valem ao mesmo tempo,
# a condição 4 JÁ vale — ela é implicada pelas outras duas, não uma
# checagem independente contra AFROUXAMENTO.
#
# O que ELA isola de verdade é a direção contrária — um mutante que
# APERTE o limite (`>= 2` -> `>= 3`): o teste abaixo fixa exatamente DUAS
# partidas (o mínimo que a condição permite) com tudo mais correto, e
# teria de reprovar sob esse mutante.
# ---------------------------------------------------------------------------


def test_condicao4_duas_partidas_e_o_minimo_que_ainda_fecha(client, cen):
    """Isola a condição 4 contra um APERTO do limite (`>= 2` -> `>= 3`):
    exatamente duas partidas válidas, tudo mais no estado que permite
    "Fecha". Sob o mutante que exigisse três, este teste reprovaria."""
    _login(client)
    resposta = client.post(
        _url_tela(cen),
        _duas_linhas(
            cen,
            valor_debito="10,00",
            valor_credito="10,00",
            acao="adicionar_linha",
            chave="k-bl312-c4-minimo",
        ),
    )
    assert resposta.status_code == 200
    assert resposta.context["veredito_fechamento"] == "fecha"


def test_condicao4_uma_partida_valida_nao_fecha_nem_com_valor_zero(client, cen):
    """Complemento honesto (não isola a condição 4 sozinha — ver a nota
    acima): com só UMA partida válida, débito == crédito só é possível
    com os dois em zero, e aí é a condição 2 que reprova primeiro. Registra
    o comportamento real, sem fingir que este caso separa a condição 4 das
    demais."""
    _login(client)
    resposta = client.post(
        _url_tela(cen),
        {
            "acao": "adicionar_linha",
            "num_linhas": "2",
            "data": timezone.localdate().isoformat(),
            "historico": "BL-312",
            "chave_idempotencia": "k-bl312-c4-uma-partida",
            "conta_1": str(cen["caixa"].id),
            "tipo_1": "debito",
            "valor_1": "50,00",
            "conta_2": "",
            "tipo_2": "",
            "valor_2": "",
        },
    )
    assert resposta.status_code == 200
    assert resposta.context["veredito_fechamento"] == "nao_conferido"


# ---------------------------------------------------------------------------
# Condição 5 — not bloqueado_por_outro_erro (BL-307, acrescentada nesta
# rodada: histórico, chave de idempotência ou data inválidos, sem relação
# com débito, crédito ou linha excluída). Só existe no caminho de
# GRAVAÇÃO — "adicionar_linha" nunca valida histórico/chave/data, então a
# condição não tem como ser isolada nesse caminho (ela sempre vale lá).
# ---------------------------------------------------------------------------


def test_condicao5_bloqueado_por_outro_erro_e_a_unica_que_decide(client, cen):
    """Isolada: duas partidas válidas BATENDO (condições 1, 2, 3 e 4
    valem), mas histórico maior que o teto do modelo — o motivo que o
    BL-307 identificou como não coberto pela correção de `linhas_
    excluidas_do_total` sozinha. Só a condição 5 falha — resultado
    `"nao_conferido"`, numa resposta 400 (não pode ser "fecha": é
    exatamente o achado A1 da auditoria DL-024 rodada 3)."""
    _login(client)
    corpo = _duas_linhas(
        cen,
        valor_debito="500,00",
        valor_credito="500,00",
        acao="gravar",
        chave="k-bl312-c5",
        historico="x" * (TAMANHO_MAXIMO_HISTORICO + 1),
    )

    resposta = client.post(_url_tela(cen), corpo)

    assert resposta.status_code == 400
    assert resposta.context["linhas_excluidas_do_total"] == 0
    assert resposta.context["veredito_fechamento"] == "nao_conferido"
    assert LancamentoContabil.objects.filter(chave_idempotencia="k-bl312-c5").count() == 0
