"""BL-149 / achado R6-2: a política dos cinco dicionários nas rotas de escrita
de `apps.empresas`.

Medido pelo auditor, tudo com sucesso e dado ignorado em silêncio:

| Rota | Dicionário | Antes |
|---|---|---|
| `POST …/estabelecimentos/` | `empresa: 999`, `xpto` no corpo | **201** |
| `POST …/regime-tributario/` | querystring; `empresa`, `xpto` no corpo | **201** |

`empresa` no corpo é o campo que mais engana: o vínculo real vem SEMPRE do
escopo da URL, revalidado contra o escritório ativo — então nunca houve
vazamento —, mas quem o envia acredita ter escolhido a empresa e recebia 201.

Acrescento as rotas que a rodada 6 NÃO mediu e que são a mesma superfície de
escrita (item 2 da DE-034): `POST …/empresas/`, `PUT`/`PATCH …/empresas/<id>/`
e o `DELETE` de regime tributário criado nesta etapa. Fechar só o que foi
medido é como o vizinho escapa.
"""

from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.empresas.models import (
    Empresa,
    Estabelecimento,
    HistoricoRegimeTributario,
    RegimeTributario,
)
from apps.empresas.services import registrar_regime_tributario
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"
CNPJ_VALIDO_NOVO = "ab123cde000155"


@pytest.fixture
def cenario():
    escritorio = Escritorio.objects.create(nome="Escritório BL-149/E", cnpj="13131313000144")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa BL-149/E Ltda", cnpj="11222333000181"
    )
    usuario = get_user_model().objects.create_user(
        username="gestora-bl149e", email="gestora-bl149e@escritorio.com.br", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return {"escritorio": escritorio, "empresa": empresa}


@pytest.fixture
def autenticado(client, cenario):
    assert client.login(username="gestora-bl149e", password=SENHA)
    return client


# ---------------------------------------------------------------------------
# POST /empresas/api/empresas/
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("campo", ["escritorio", "xpto", "id", "regime_atual"])
def test_criacao_de_empresa_recusa_campo_desconhecido(autenticado, campo):
    """`escritorio` e `regime_atual` são os dois casos de fundo: o primeiro é
    campo de ISOLAMENTO (o serializer o define a partir do escritório ativo) e
    o segundo é `read_only`. Nos dois, quem envia acredita ter escolhido algo
    que o servidor decide."""
    resposta = autenticado.post(
        reverse("empresas:api-lista"),
        {"razao_social": "Nova Ltda", "cnpj": CNPJ_VALIDO_NOVO, campo: 999},
        content_type="application/json",
    )

    assert resposta.status_code == 400, (campo, resposta.status_code, resposta.content)
    assert campo in resposta.content.decode()
    assert Empresa.objects.count() == 1


def test_criacao_de_empresa_recusa_querystring(autenticado):
    resposta = autenticado.post(
        reverse("empresas:api-lista") + "?utm_source=email",
        {"razao_social": "Nova Ltda", "cnpj": CNPJ_VALIDO_NOVO},
        content_type="application/json",
    )

    assert resposta.status_code == 400, (resposta.status_code, resposta.content)
    assert Empresa.objects.count() == 1


def test_criacao_de_empresa_dentro_do_contrato_continua_funcionando(autenticado, cenario):
    resposta = autenticado.post(
        reverse("empresas:api-lista"),
        {"razao_social": "Nova Ltda", "cnpj": CNPJ_VALIDO_NOVO, "ativo": True},
        content_type="application/json",
    )

    assert resposta.status_code == 201, (resposta.status_code, resposta.content)
    criada = Empresa.objects.get(razao_social="Nova Ltda")
    # Isolamento preservado: o escritório continua vindo do ativo, não do corpo.
    assert criada.escritorio_id == cenario["escritorio"].pk


def test_alteracao_de_empresa_recusa_campo_desconhecido(autenticado, cenario):
    """A rodada 6 mediu a CRIAÇÃO; esta é a rota vizinha, com o mesmo corpo."""
    resposta = autenticado.patch(
        reverse("empresas:api-detalhe", args=[cenario["empresa"].pk]),
        {"razao_social": "Outro Nome Ltda", "xpto": 1},
        content_type="application/json",
    )

    assert resposta.status_code == 400, (resposta.status_code, resposta.content)
    cenario["empresa"].refresh_from_db()
    assert cenario["empresa"].razao_social == "Empresa BL-149/E Ltda"


def test_alteracao_de_empresa_dentro_do_contrato_continua_funcionando(autenticado, cenario):
    resposta = autenticado.patch(
        reverse("empresas:api-detalhe", args=[cenario["empresa"].pk]),
        {"razao_social": "Outro Nome Ltda"},
        content_type="application/json",
    )

    assert resposta.status_code == 200, (resposta.status_code, resposta.content)
    cenario["empresa"].refresh_from_db()
    assert cenario["empresa"].razao_social == "Outro Nome Ltda"


# ---------------------------------------------------------------------------
# POST .../estabelecimentos/
# ---------------------------------------------------------------------------


def _corpo_de_estabelecimento():
    return {"tipo": "matriz", "nome": "Matriz", "cnpj": CNPJ_VALIDO_NOVO}


@pytest.mark.parametrize("campo", ["empresa", "xpto"])
def test_estabelecimento_recusa_campo_desconhecido(autenticado, cenario, campo):
    resposta = autenticado.post(
        reverse("empresas:api-estabelecimentos", args=[cenario["empresa"].pk]),
        {**_corpo_de_estabelecimento(), campo: 999},
        content_type="application/json",
    )

    assert resposta.status_code == 400, (campo, resposta.status_code, resposta.content)
    assert not Estabelecimento.objects.exists()


def test_estabelecimento_recusa_arquivo(autenticado, cenario):
    with open(__file__, "rb") as arquivo:
        resposta = autenticado.post(
            reverse("empresas:api-estabelecimentos", args=[cenario["empresa"].pk]),
            {**_corpo_de_estabelecimento(), "contrato": arquivo},
        )

    assert resposta.status_code == 400, (resposta.status_code, resposta.content)
    assert not Estabelecimento.objects.exists()


def test_estabelecimento_dentro_do_contrato_continua_funcionando(autenticado, cenario):
    resposta = autenticado.post(
        reverse("empresas:api-estabelecimentos", args=[cenario["empresa"].pk]),
        _corpo_de_estabelecimento(),
        content_type="application/json",
    )

    assert resposta.status_code == 201, (resposta.status_code, resposta.content)
    assert Estabelecimento.objects.get().empresa_id == cenario["empresa"].pk


# ---------------------------------------------------------------------------
# POST e DELETE .../regime-tributario/
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("campo", ["empresa", "xpto", "vigencia_fim"])
def test_regime_recusa_campo_desconhecido(autenticado, cenario, campo):
    """`vigencia_fim` entra na lista porque é `read_only` no serializer: quem o
    envia acredita estar fechando o período à mão, e quem fecha é o serviço."""
    resposta = autenticado.post(
        reverse("empresas:api-regime-tributario", args=[cenario["empresa"].pk]),
        {"regime": "simples_nacional", "vigencia_inicio": "2024-01-01", campo: "2024-12-31"},
        content_type="application/json",
    )

    assert resposta.status_code == 400, (campo, resposta.status_code, resposta.content)
    assert not HistoricoRegimeTributario.objects.exists()


def test_regime_recusa_querystring(autenticado, cenario):
    url = reverse("empresas:api-regime-tributario", args=[cenario["empresa"].pk])

    resposta = autenticado.post(
        f"{url}?empresa=999",
        {"regime": "simples_nacional", "vigencia_inicio": "2024-01-01"},
        content_type="application/json",
    )

    assert resposta.status_code == 400, (resposta.status_code, resposta.content)
    assert not HistoricoRegimeTributario.objects.exists()


def test_exclusao_de_regime_recusa_corpo_e_nao_apaga(autenticado, cenario):
    registro = registrar_regime_tributario(
        cenario["empresa"], RegimeTributario.SIMPLES_NACIONAL, date(2024, 1, 1)
    )
    url = reverse(
        "empresas:api-regime-tributario-detalhe", args=[cenario["empresa"].pk, registro.pk]
    )

    resposta = autenticado.delete(
        url, {"vigencia_inicio": "2024-01-01"}, content_type="application/json"
    )

    assert resposta.status_code == 400, (resposta.status_code, resposta.content)
    assert HistoricoRegimeTributario.objects.filter(pk=registro.pk).exists()
