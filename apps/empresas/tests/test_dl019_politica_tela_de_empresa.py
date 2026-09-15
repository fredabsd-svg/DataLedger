"""A política dos cinco dicionários na TELA de cadastro de empresa
(BL-196, superfície encontrada pela varredura da segunda rodada da DL-020).

`criar_empresa` era a única superfície de escrita do repositório que ainda
não aplicava `apps.core.requisicao` — e não estava em nenhum relatório de
auditoria, porque a rodada 6 mediu `conta_nova` e `ativar_escritorio` e o
fechamento cobriu as rotas de API. Foi a **varredura** que a apontou, que é
precisamente o que ela existe para fazer: *a conferência manual não reprova
build*.

A classe do defeito é a mesma de `conta_nova`: um campo enviado como ARQUIVO
não aparece em `request.POST` — o `ModelForm` o trata como ausente — e um
campo desconhecido era lido por ninguém, sem uma palavra ao usuário.

Em todo caso de recusa, duas asserções:

1. **400**, com o formulário re-renderizado e o que foi digitado de volta.
2. **Nada gravado.** A primeira sozinha não bastaria: o defeito da família é
   gravar (ou deixar de gravar) com aparência de sucesso.
"""

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.empresas.forms import EmpresaForm
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"
CNPJ_VALIDO = "11122233000183"


@pytest.fixture
def escritorio():
    return Escritorio.objects.create(nome="Escritório BL-196/T", cnpj="11111111000111")


@pytest.fixture
def autenticado(client, escritorio):
    usuario = get_user_model().objects.create_user(
        username="gestora-bl149t", email="gestora-bl149t@escritorio.com.br", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    assert client.login(username="gestora-bl149t", password=SENHA)
    return client


def _mensagens(resposta):
    return [str(m) for m in resposta.context["messages"]]


def _corpo_valido():
    return {"razao_social": "Empresa Nova Ltda", "nome_fantasia": "", "cnpj": CNPJ_VALIDO}


def test_tela_recusa_arquivo_com_400_e_nao_grava(autenticado):
    corpo = _corpo_valido()
    corpo["cnpj"] = SimpleUploadedFile("cnpj.txt", CNPJ_VALIDO.encode(), content_type="text/plain")

    resposta = autenticado.post(reverse("empresas:criar"), corpo)

    assert resposta.status_code == 400, resposta.status_code
    assert any("não aceita arquivo nenhum" in m for m in _mensagens(resposta))
    assert not Empresa.objects.exists()


def test_tela_recusa_querystring_em_post_com_400_e_nao_grava(autenticado):
    resposta = autenticado.post(reverse("empresas:criar") + "?razao_social=Outra", _corpo_valido())

    assert resposta.status_code == 400
    assert any("não aceita parâmetros na URL" in m for m in _mensagens(resposta))
    assert not Empresa.objects.exists()


def test_tela_recusa_cabecalho_de_idempotencia_com_400_e_nao_grava(autenticado):
    resposta = autenticado.post(
        reverse("empresas:criar"),
        _corpo_valido(),
        headers={"Idempotency-Key": "chave-que-esta-tela-nao-usa"},
    )

    assert resposta.status_code == 400
    assert any("Idempotency-Key" in m for m in _mensagens(resposta))
    assert not Empresa.objects.exists()


@pytest.mark.parametrize("campo", ["escritorio", "xpto", "id"])
def test_tela_recusa_campo_desconhecido_com_400_e_nao_grava(autenticado, campo):
    """`escritorio` é o caso de fundo: é campo de ISOLAMENTO (a view o define
    a partir do escritório ativo), então nunca vazou nada — mas quem o envia
    acredita ter cadastrado empresa em outro escritório e recebia sucesso."""
    corpo = _corpo_valido()
    corpo[campo] = "999"

    resposta = autenticado.post(reverse("empresas:criar"), corpo)

    assert resposta.status_code == 400
    assert any(campo in m for m in _mensagens(resposta))
    assert not Empresa.objects.exists()


def test_tela_recusada_devolve_o_que_foi_digitado(autenticado):
    """BL-199: recusar sem devolver o que o usuário digitou troca um defeito
    por outro. O formulário volta VINCULADO ao POST."""
    corpo = _corpo_valido()
    corpo["razao_social"] = "Empresa Com Nome Digitado Ltda"
    corpo["xpto"] = "1"

    resposta = autenticado.post(reverse("empresas:criar"), corpo)

    assert resposta.status_code == 400
    assert "Empresa Com Nome Digitado Ltda" in resposta.content.decode()


def test_tela_grava_quando_o_corpo_e_exatamente_o_contratado(autenticado):
    """Controle positivo, indispensável: sem ele, um mutante que recusasse
    TODA requisição não mataria nenhum dos casos acima."""
    resposta = autenticado.post(reverse("empresas:criar"), _corpo_valido(), follow=True)

    assert resposta.status_code == 200
    assert Empresa.objects.filter(cnpj=CNPJ_VALIDO).exists()
    assert any("cadastrada com sucesso" in m for m in _mensagens(resposta))


def test_o_contrato_da_tela_acompanha_os_campos_do_formulario():
    """O contrato é derivado de `EmpresaForm.fields`, não de uma lista
    literal. Se um campo novo entrar no formulário e o contrato não o
    acompanhar, a tela passaria a recusar um campo que o próprio `<form>`
    emite — recusa de dado LEGÍTIMO, que é o defeito oposto e igualmente
    ruim. Este teste prende os dois lados juntos.
    """
    from apps.empresas.views import _contrato_da_tela_de_empresa

    contrato = _contrato_da_tela_de_empresa()

    assert contrato.campos == frozenset(EmpresaForm().fields) | {"csrfmiddlewaretoken"}
    assert contrato.aceita_arquivo is False
    assert contrato.aceita_querystring is False
