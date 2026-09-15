"""BL-196 / achado R6-2: a política dos cinco dicionários nas rotas de
ESCRITA da API de contabilidade.

O que o auditor mediu, autenticado e com payload válido — todas devolvendo
sucesso com o dado ignorado em silêncio:

| Rota | Dicionário | Antes |
|---|---|---|
| `POST …/lancamentos/` | querystring `?conta_3=…&xpto=1` | **201** |
| `POST …/contas/` | querystring; `empresa: 999`, `xpto`, `id: 4242` no corpo | **201** |

O critério da BL-145 dizia "em nenhuma superfície e em nenhum dicionário", e
fechou em 1 de 7. Aqui ficam as três rotas de escrita deste app; as de
`empresas` e `tenancy` têm arquivo irmão em cada app, e as duas telas são do
`especialista-frontend`.

Cada caso verifica as duas coisas que o achado tinha juntas: **400** (não
sucesso) e **nada gravado** — um 400 que já tivesse gravado seria pior que o
201 original.
"""

from datetime import date
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
from apps.contabilidade.services import criar_lancamento
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"


@pytest.fixture
def cenario():
    escritorio = Escritorio.objects.create(nome="Escritório BL-196", cnpj="12121212000133")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa BL-196 Ltda", cnpj="11222333000181"
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
        username="gestora-bl149", email="gestora-bl149@escritorio.com.br", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return {"escritorio": escritorio, "empresa": empresa, "caixa": caixa, "receita": receita}


@pytest.fixture
def autenticado(client, cenario):
    assert client.login(username="gestora-bl149", password=SENHA)
    return client


def _corpo_de_lancamento(cenario):
    return {
        "data": timezone.localdate().isoformat(),
        "historico": "BL-196",
        "itens": [
            {"conta": cenario["caixa"].id, "tipo": "debito", "valor": "10.00"},
            {"conta": cenario["receita"].id, "tipo": "credito", "valor": "10.00"},
        ],
    }


def _corpo_de_conta():
    return {
        "codigo": "3",
        "nome": "Conta nova",
        "tipo": TipoConta.DESPESA,
        "natureza": NaturezaConta.DEVEDORA,
    }


def _nenhum_lancamento():
    return not LancamentoContabil.objects.exists() and not ItemLancamento.objects.exists()


# ---------------------------------------------------------------------------
# POST .../contas/
# ---------------------------------------------------------------------------


def test_conta_com_querystring_no_post_e_recusada(autenticado, cenario):
    url = reverse("contabilidade:contas", args=[cenario["empresa"].id])

    resposta = autenticado.post(
        f"{url}?conta_pai=999&xpto=1", _corpo_de_conta(), content_type="application/json"
    )

    assert resposta.status_code == 400, (resposta.status_code, resposta.content)
    assert "xpto" in resposta.content.decode()
    assert Conta.objects.count() == 2  # só as duas do cenário


@pytest.mark.parametrize("campo", ["empresa", "xpto", "id"])
def test_conta_com_campo_desconhecido_no_corpo_e_recusada(autenticado, cenario, campo):
    """`id: 4242` é o pior dos três: quem o envia acredita ter escolhido o
    identificador do registro, e recebia 201 com outro id."""
    url = reverse("contabilidade:contas", args=[cenario["empresa"].id])
    corpo = {**_corpo_de_conta(), campo: 4242}

    resposta = autenticado.post(url, corpo, content_type="application/json")

    assert resposta.status_code == 400, (campo, resposta.status_code, resposta.content)
    assert campo in resposta.content.decode()
    assert Conta.objects.count() == 2


def test_conta_com_arquivo_e_recusada(autenticado, cenario):
    """O caso A3/BL-128 na rota irmã: `conta_pai` como ARQUIVO era invisível
    para quem só olha o corpo decodificado."""
    url = reverse("contabilidade:contas", args=[cenario["empresa"].id])

    with open(__file__, "rb") as arquivo:
        resposta = autenticado.post(url, {**_corpo_de_conta(), "conta_pai": arquivo})

    assert resposta.status_code == 400, (resposta.status_code, resposta.content)
    assert Conta.objects.count() == 2


def test_conta_com_cabecalho_de_idempotencia_e_recusada(autenticado, cenario):
    """Esta rota NÃO implementa idempotência (só o POST de lançamento
    implementa). Quem manda a chave aqui acredita estar protegido contra
    duplicidade e não está — é o R5-6 na direção oposta."""
    url = reverse("contabilidade:contas", args=[cenario["empresa"].id])

    resposta = autenticado.post(
        url,
        _corpo_de_conta(),
        content_type="application/json",
        headers={"idempotency-key": "chave-na-rota-errada"},
    )

    assert resposta.status_code == 400, (resposta.status_code, resposta.content)
    assert Conta.objects.count() == 2


def test_conta_dentro_do_contrato_continua_sendo_criada(autenticado, cenario):
    """Controle positivo: a política não pode ter apertado o caminho normal."""
    url = reverse("contabilidade:contas", args=[cenario["empresa"].id])

    resposta = autenticado.post(
        url,
        {**_corpo_de_conta(), "conta_pai": cenario["caixa"].id},
        content_type="application/json",
    )

    assert resposta.status_code == 201, (resposta.status_code, resposta.content)
    assert Conta.objects.get(codigo="3").conta_pai_id == cenario["caixa"].pk


# ---------------------------------------------------------------------------
# POST .../lancamentos/
# ---------------------------------------------------------------------------


def test_lancamento_com_querystring_e_recusado(autenticado, cenario):
    """O caso medido: um par de partidas COMPLETO pendurado na querystring, ao
    lado de duas partidas normais no corpo — gravava só as do corpo, com 201."""
    url = reverse("contabilidade:lancamentos", args=[cenario["empresa"].id])

    resposta = autenticado.post(
        f"{url}?conta_3={cenario['caixa'].id}&xpto=1",
        _corpo_de_lancamento(cenario),
        content_type="application/json",
    )

    assert resposta.status_code == 400, (resposta.status_code, resposta.content)
    assert _nenhum_lancamento()


def test_lancamento_com_arquivo_e_recusado(autenticado, cenario):
    url = reverse("contabilidade:lancamentos", args=[cenario["empresa"].id])

    with open(__file__, "rb") as arquivo:
        resposta = autenticado.post(
            url,
            {
                "data": timezone.localdate().isoformat(),
                "historico": "com arquivo",
                "anexo": arquivo,
            },
        )

    assert resposta.status_code == 400, (resposta.status_code, resposta.content)
    assert _nenhum_lancamento()


def test_lancamento_continua_aceitando_o_cabecalho_de_idempotencia(autenticado, cenario):
    """Controle de contrato: `Idempotency-Key` é o contrato REAL desta rota
    (BL-41) e não pode ser recusado junto com os cabeçalhos que as outras
    ignoram — recusá-lo aqui quebraria a única proteção contra duplicidade que
    a API oferece."""
    url = reverse("contabilidade:lancamentos", args=[cenario["empresa"].id])
    corpo = _corpo_de_lancamento(cenario)

    primeira = autenticado.post(
        url, corpo, content_type="application/json", headers={"idempotency-key": "bl149"}
    )
    segunda = autenticado.post(
        url, corpo, content_type="application/json", headers={"idempotency-key": "bl149"}
    )

    assert primeira.status_code == 201, (primeira.status_code, primeira.content)
    assert segunda.status_code == 200, (segunda.status_code, segunda.content)
    assert LancamentoContabil.objects.count() == 1


# ---------------------------------------------------------------------------
# POST .../lancamentos/<id>/estornar/
# ---------------------------------------------------------------------------


@pytest.fixture
def lancamento(cenario):
    return criar_lancamento(
        empresa=cenario["empresa"],
        data=date(2024, 1, 10),
        historico="para estornar",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("10.00")},
            {"conta": cenario["receita"], "tipo": TipoPartida.CREDITO, "valor": Decimal("10.00")},
        ],
    )


@pytest.mark.parametrize(
    "extra",
    [
        {"corpo": {"data": "2024-01-01"}},
        {"corpo": {"historico": "meu estorno"}},
        {"querystring": "?data=2024-01-01"},
        {"cabecalho": {"idempotency-key": "x"}},
    ],
)
def test_estorno_recusa_dado_nao_contratado(autenticado, cenario, lancamento, extra):
    """Rota de AÇÃO, e é por isso que ela importa: um corpo com `data` sugere
    ao cliente que ele está datando o estorno, quando a data é decidida pelo
    servidor (RC-78). Aceitar e ignorar produziria um estorno com data
    diferente da que o cliente acredita ter pedido — consequência contábil, não
    só cosmética."""
    url = reverse("contabilidade:estornar", args=[cenario["empresa"].id, lancamento.pk])
    url = url + extra.get("querystring", "")

    resposta = autenticado.post(
        url,
        extra.get("corpo", {}),
        content_type="application/json",
        headers=extra.get("cabecalho", {}),
    )

    assert resposta.status_code == 400, (extra, resposta.status_code, resposta.content)
    assert not lancamento.estornos.exists()


def test_estorno_sem_corpo_continua_funcionando(autenticado, cenario, lancamento):
    url = reverse("contabilidade:estornar", args=[cenario["empresa"].id, lancamento.pk])

    resposta = autenticado.post(url)

    assert resposta.status_code == 201, (resposta.status_code, resposta.content)
    assert lancamento.estornos.count() == 1
