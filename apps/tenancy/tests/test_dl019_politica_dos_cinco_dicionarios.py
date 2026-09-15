"""A política dos cinco dicionários nas DUAS superfícies de troca de
escritório ativo (BL-149, lacuna (c) do inventário de 2026-09-15).

## O que faltava

`apps/tenancy/views.py` aplica `apps.core.requisicao.recusar_dado_nao_
contratado` em `EscritorioAtivoView.post` (API, linha 94) e em
`ativar_escritorio` (tela, linha 161) — e **nenhum teste exercitava nenhuma
das duas**. É onde o gêmeo do BL-127 foi encontrado: a tela e a API deste
app já divergiram uma vez, com o defeito de identificador corrigido de um
lado e não do outro. Código de política sem teste é código que a próxima
correção pode remover sem nada acusar.

O auditor mediu, antes da correção do R6-2:

| Superfície | Enviado | Antes |
|---|---|---|
| tela `POST /ativar/` | querystring | **302**, em silêncio |
| tela `POST /ativar/` | campo desconhecido | **302**, em silêncio |
| tela `POST /ativar/` | `request.FILES` | **302**, em silêncio |
| API `POST /api/escritorio-ativo/` | `xpto` no corpo | **200** |

## Os cinco dicionários, e como cada um aparece aqui

**Arquivo, querystring, cabeçalho e corpo** têm caso próprio, nas duas
superfícies. O **corpo bruto** não tem, e isso é o que
`apps.core.requisicao` declara no seu docstring: ele só chega ao sistema pelo
decodificador da superfície, e um corpo que o decodificador não entenda já
produz 400 do parser ou dicionário vazio — nunca gravação com aparência de
sucesso. Registrar isso aqui é o que impede que "quatro casos" pareça
esquecimento do quinto.

## Duas asserções em todo caso de recusa, sempre

1. A superfície **diz não** (mensagem de erro na tela, 400 na API).
2. **A troca não aconteceu** (`session["escritorio_id"]` intacto). A primeira
   sozinha não bastaria: o defeito original era justamente a troca
   acontecendo — ou não acontecendo — sem ninguém avisar, e uma recusa
   colocada DEPOIS da gravação não repara nada (é o que o módulo da política
   avisa em `recusar_dado_nao_contratado`).
"""

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.core.requisicao import (
    DICIONARIO_ARQUIVO,
    DICIONARIO_CABECALHO,
    DICIONARIO_CORPO,
    DICIONARIO_QUERYSTRING,
    ORDEM_DE_AVALIACAO,
)
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"
URL_TELA = "tenancy:ativar"
URL_API = "tenancy:api-escritorio-ativo"


@pytest.fixture
def cenario():
    Usuario = get_user_model()
    escritorio_a = Escritorio.objects.create(nome="Escritório A", cnpj="11111111000111")
    escritorio_b = Escritorio.objects.create(nome="Escritório B", cnpj="22222222000122")
    usuario = Usuario.objects.create_user(
        username="ana-bl149", email="ana-bl149@escritorio.com.br", password=SENHA
    )
    for escritorio in (escritorio_a, escritorio_b):
        VinculoUsuarioEscritorio.objects.create(
            usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
        )
    return {"usuario": usuario, "escritorio_a": escritorio_a, "escritorio_b": escritorio_b}


@pytest.fixture
def autenticado(client, cenario):
    assert client.login(username="ana-bl149", password=SENHA)
    return client


@pytest.fixture
def com_escritorio_a_ativo(autenticado, cenario):
    """Deixa o escritório A ativo ANTES do caso de teste.

    É o que permite afirmar que a recusa não trocou nada: com a sessão vazia,
    "não trocou" e "trocou para o escritório errado e depois desfez" podem
    produzir o mesmo `None`. Com A ativo, qualquer efeito da requisição
    recusada apareceria como mudança de valor.
    """
    resposta = autenticado.post(
        reverse(URL_TELA), {"escritorio_id": cenario["escritorio_a"].id}, follow=True
    )
    assert resposta.status_code == 200
    assert autenticado.session["escritorio_id"] == cenario["escritorio_a"].id
    return autenticado


def _mensagens(resposta):
    return [str(m) for m in resposta.context["messages"]]


def _arquivo():
    return SimpleUploadedFile("qualquer.txt", b"conteudo", content_type="text/plain")


# ---------------------------------------------------------------------------
# Tela: POST /ativar/
# ---------------------------------------------------------------------------


def test_tela_recusa_arquivo_e_nao_troca(com_escritorio_a_ativo, cenario):
    """A3/BL-128 na superfície de tenancy: um campo enviado como ARQUIVO não
    aparece em `request.POST`. Antes, a troca seguia adiante com o dicionário
    que o servidor NÃO leu, e o resultado era 302 de sucesso."""
    resposta = com_escritorio_a_ativo.post(
        reverse(URL_TELA),
        {"escritorio_id": cenario["escritorio_b"].id, "anexo": _arquivo()},
        follow=True,
    )

    assert resposta.status_code == 200
    assert any("não aceita arquivo nenhum" in m for m in _mensagens(resposta))
    assert any("anexo" in m for m in _mensagens(resposta))
    assert com_escritorio_a_ativo.session["escritorio_id"] == cenario["escritorio_a"].id


def test_tela_recusa_querystring_em_post_e_nao_troca(com_escritorio_a_ativo, cenario):
    resposta = com_escritorio_a_ativo.post(
        reverse(URL_TELA) + "?escritorio_id=" + str(cenario["escritorio_b"].id),
        {"escritorio_id": cenario["escritorio_b"].id},
        follow=True,
    )

    assert resposta.status_code == 200
    assert any("não aceita parâmetros na URL" in m for m in _mensagens(resposta))
    assert com_escritorio_a_ativo.session["escritorio_id"] == cenario["escritorio_a"].id


def test_tela_recusa_cabecalho_de_idempotencia_e_nao_troca(com_escritorio_a_ativo, cenario):
    """Trocar de escritório é idempotente por natureza, então esta superfície
    não tem contrato de `Idempotency-Key` nenhum. Quem a envia está usando um
    contrato que não existe — é o R5-6 na direção oposta: lá a chave ignorada
    produzia duplicidade; aqui ela produziria a impressão de um controle de
    repetição que ninguém implementou."""
    resposta = com_escritorio_a_ativo.post(
        reverse(URL_TELA),
        {"escritorio_id": cenario["escritorio_b"].id},
        follow=True,
        headers={"Idempotency-Key": "chave-que-esta-tela-nao-usa"},
    )

    assert resposta.status_code == 200
    assert any("Idempotency-Key" in m for m in _mensagens(resposta))
    assert com_escritorio_a_ativo.session["escritorio_id"] == cenario["escritorio_a"].id


def test_tela_recusa_campo_desconhecido_no_corpo_e_nao_troca(com_escritorio_a_ativo, cenario):
    resposta = com_escritorio_a_ativo.post(
        reverse(URL_TELA),
        {"escritorio_id": cenario["escritorio_b"].id, "xpto": "1"},
        follow=True,
    )

    assert resposta.status_code == 200
    mensagens = _mensagens(resposta)
    assert any("xpto" in m for m in mensagens), mensagens
    assert com_escritorio_a_ativo.session["escritorio_id"] == cenario["escritorio_a"].id


def test_tela_troca_de_verdade_quando_o_corpo_e_exatamente_o_contratado(
    com_escritorio_a_ativo, cenario
):
    """Controle positivo, e ele é indispensável: sem este teste, um mutante
    que recusasse TODA requisição (`if True: raise DadoNaoContratado`) mataria
    zero dos casos acima — todos eles esperam recusa."""
    resposta = com_escritorio_a_ativo.post(
        reverse(URL_TELA), {"escritorio_id": cenario["escritorio_b"].id}, follow=True
    )

    assert resposta.status_code == 200
    assert any("Escritório ativo: Escritório B" in m for m in _mensagens(resposta))
    assert com_escritorio_a_ativo.session["escritorio_id"] == cenario["escritorio_b"].id


def test_tela_recusa_o_arquivo_antes_da_querystring(com_escritorio_a_ativo, cenario):
    """`ORDEM_DE_AVALIACAO` é comportamento observável (o módulo da política
    declara isso): com duas violações na mesma requisição, a mensagem que o
    contador vê é a da PRIMEIRA da ordem. Um mutante que reordenasse a
    avaliação trocaria a mensagem sem quebrar nenhum dos casos de violação
    única acima."""
    assert ORDEM_DE_AVALIACAO.index(DICIONARIO_ARQUIVO) < ORDEM_DE_AVALIACAO.index(
        DICIONARIO_QUERYSTRING
    )

    resposta = com_escritorio_a_ativo.post(
        reverse(URL_TELA) + "?xpto=1",
        {"escritorio_id": cenario["escritorio_b"].id, "anexo": _arquivo()},
        follow=True,
    )

    mensagens = _mensagens(resposta)
    assert any("não aceita arquivo nenhum" in m for m in mensagens), mensagens
    assert not any("não aceita parâmetros na URL" in m for m in mensagens), mensagens
    assert com_escritorio_a_ativo.session["escritorio_id"] == cenario["escritorio_a"].id


# ---------------------------------------------------------------------------
# API: POST /api/escritorio-ativo/
# ---------------------------------------------------------------------------


def test_api_recusa_arquivo_com_400_e_nao_troca(com_escritorio_a_ativo, cenario):
    resposta = com_escritorio_a_ativo.post(
        reverse(URL_API),
        {"escritorio_id": cenario["escritorio_b"].id, "anexo": _arquivo()},
    )

    assert resposta.status_code == 400, resposta.content
    assert "não aceita arquivo nenhum" in resposta.json()["detail"]
    assert com_escritorio_a_ativo.session["escritorio_id"] == cenario["escritorio_a"].id


def test_api_recusa_querystring_com_400_e_nao_troca(com_escritorio_a_ativo, cenario):
    resposta = com_escritorio_a_ativo.post(
        reverse(URL_API) + "?escritorio_id=" + str(cenario["escritorio_b"].id),
        data={"escritorio_id": cenario["escritorio_b"].id},
        content_type="application/json",
    )

    assert resposta.status_code == 400, resposta.content
    assert "não aceita parâmetros na URL" in resposta.json()["detail"]
    assert com_escritorio_a_ativo.session["escritorio_id"] == cenario["escritorio_a"].id


def test_api_recusa_cabecalho_de_idempotencia_com_400_e_nao_troca(com_escritorio_a_ativo, cenario):
    resposta = com_escritorio_a_ativo.post(
        reverse(URL_API),
        data={"escritorio_id": cenario["escritorio_b"].id},
        content_type="application/json",
        headers={"Idempotency-Key": "chave-que-esta-rota-nao-usa"},
    )

    assert resposta.status_code == 400, resposta.content
    assert "Idempotency-Key" in resposta.json()["detail"]
    assert com_escritorio_a_ativo.session["escritorio_id"] == cenario["escritorio_a"].id


@pytest.mark.parametrize("campo", ["xpto", "escritorio", "id"])
def test_api_recusa_campo_desconhecido_no_corpo_com_400_e_nao_troca(
    com_escritorio_a_ativo, cenario, campo
):
    """`escritorio` e `id` não são invenções: são os nomes que um cliente
    naturalmente tentaria em vez de `escritorio_id`, e aceitá-los em silêncio
    faria a requisição parecer bem-sucedida sem ter trocado nada (ou, pior,
    tendo trocado para o valor de `escritorio_id` que o cliente acreditava
    estar sobrepondo)."""
    resposta = com_escritorio_a_ativo.post(
        reverse(URL_API),
        data={"escritorio_id": cenario["escritorio_b"].id, campo: 999},
        content_type="application/json",
    )

    assert resposta.status_code == 400, resposta.content
    assert campo in resposta.json()["detail"]
    assert com_escritorio_a_ativo.session["escritorio_id"] == cenario["escritorio_a"].id


def test_api_troca_de_verdade_quando_o_corpo_e_exatamente_o_contratado(
    com_escritorio_a_ativo, cenario
):
    """Mesmo papel do controle positivo da tela — ver o comentário lá."""
    resposta = com_escritorio_a_ativo.post(
        reverse(URL_API),
        data={"escritorio_id": cenario["escritorio_b"].id},
        content_type="application/json",
    )

    assert resposta.status_code == 200, resposta.content
    assert resposta.json() == {"status": "ok"}
    assert com_escritorio_a_ativo.session["escritorio_id"] == cenario["escritorio_b"].id


def test_as_duas_superficies_usam_o_mesmo_contrato(com_escritorio_a_ativo, cenario):
    """DE-026 virada teste: uma política, um lugar.

    A tela e a API compartilham `CONTRATO_ESCRITORIO_ATIVO` — o mesmo objeto,
    não duas declarações parecidas. Se alguém der a uma das superfícies um
    contrato próprio, a divergência nasce aqui, e foi assim que o gêmeo do
    BL-127 existiu: a mesma regra corrigida num lado e não no outro.
    """
    import inspect

    from apps.tenancy import views

    assert views.CONTRATO_ESCRITORIO_ATIVO.campos == frozenset({"escritorio_id"})
    assert views.CONTRATO_ESCRITORIO_ATIVO.aceita_arquivo is False
    assert views.CONTRATO_ESCRITORIO_ATIVO.aceita_querystring is False
    assert views.CONTRATO_ESCRITORIO_ATIVO.cabecalhos_ignorados == ("Idempotency-Key",)

    # Escopado na FUNÇÃO/MÉTODO citado, com parêntese de chamada — o molde da
    # BL-150: `"CONTRATO_ESCRITORIO_ATIVO" in inspect.getsource(views)` seria
    # permanentemente verdadeiro por causa da própria declaração e dos
    # comentários do arquivo.
    for fonte in (
        inspect.getsource(views.EscritorioAtivoView.post),
        inspect.getsource(views.ativar_escritorio),
    ):
        assert "recusar_dado_nao_contratado(request, CONTRATO_ESCRITORIO_ATIVO)" in fonte


def test_os_quatro_dicionarios_julgados_aqui_sao_os_da_ordem_declarada():
    """O quinto dicionário (corpo BRUTO) não tem caso de teste, e o motivo
    está no docstring do módulo. Esta asserção existe para que "quatro casos"
    nunca passe por esquecimento do quinto: a ordem declarada em
    `apps.core.requisicao` tem exatamente estes quatro, e um dicionário novo
    que apareça lá reprova aqui até alguém decidir como esta superfície o
    julga."""
    assert ORDEM_DE_AVALIACAO == (
        DICIONARIO_ARQUIVO,
        DICIONARIO_QUERYSTRING,
        DICIONARIO_CABECALHO,
        DICIONARIO_CORPO,
    )
