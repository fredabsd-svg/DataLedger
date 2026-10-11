"""DL-086 (BL-584) — o papel é checado ANTES de resolver a empresa.

Defeito fechado aqui: nas rotas WEB de contabilidade, a ordem antiga era
"resolve a empresa (404 se não existe) → checa o papel (403)". Para o papel
CLIENTE — que não lê a contabilidade — isso era um ORÁCULO DE EXISTÊNCIA:
403 para empresa existente do próprio escritório, 404 para inexistente. A
auditoria da DL-055 mediu 61 combinações de rota e método; o achado ficou
registrado como BL-584.

Correção: `_empresa_do_escritorio_ativo` levanta `PermissionDenied` antes do
`get_object_or_404` quando o papel não lê o módulo — a resposta passa a ser
a MESMA (status e corpo) para id existente e inexistente, e o B7 da DL-038
segue preservado (a recusa não revela o modo de escrituração de ninguém).

Como na varredura da DL-038 (`test_dl038_recusa_livro_caixa.py`), as rotas
são DERIVADAS de `apps.contabilidade.urls_web.urlpatterns` — nenhuma lista
escrita à mão. Uma rota nova com `empresa_id` entra nesta varredura sem
ninguém editar este arquivo; os métodos aceitos vêm da sonda TRACE (cabeçalho
`Allow` do 405), sem executar o handler. O controle de vacuidade é o par de
testes finais: papel que LÊ com id inexistente continua 404 (isolamento,
critério 2 da DL-015) — se a guarda virasse "403 para todos", aquele par
caía junto com o mutante "guarda removida" (CLIENTE com id inexistente
voltaria a ser 404).
"""

import re

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.contabilidade import urls_web as contabilidade_urls_web
from apps.contabilidade.models import Conta, LancamentoContabil
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

# Id deliberadamente absurdo: a varredura precisa de um `empresa_id` que não
# exista em escritório nenhum, e o teste abaixo confirma isso antes de usar.
ID_INEXISTENTE = 987_654_321


def _rotas_web_com_empresa_id():
    """Mesma derivação da DL-038: todo padrão de `urls_web` cujo conversor
    inclui `empresa_id`."""
    rotas = []
    for padrao in contabilidade_urls_web.urlpatterns:
        nomes_de_parametro = tuple(padrao.pattern.converters)
        if "empresa_id" in nomes_de_parametro:
            rotas.append((f"contabilidade_web:{padrao.name}", nomes_de_parametro))
    return rotas


ROTAS_WEB = _rotas_web_com_empresa_id()


def test_a_derivacao_nao_esta_vazia():
    # Controle de vacuidade: se `urls_web` for esvaziado ou a derivação
    # quebrar, este teste falha em vez de a varredura "passar" sobre zero
    # rotas. A contagem exata é fixada pela DL-038
    # (`test_a_derivacao_encontrou_as_vinte_e_quatro_rotas_web_e_as_vinte_da_api`)
    # — de propósito não duplicada aqui, para uma rota nova não exigir dois
    # arquivos editados.
    assert len(ROTAS_WEB) >= 41, ROTAS_WEB


@pytest.fixture
def cenario_cliente():
    """Escritório com uma empresa em modo contábil e um usuário CLIENTE
    vinculado. O middleware do escritório ativo resolve o vínculo único sem
    precisar de sessão prévia (mesmo padrão dos testes da DL-017/DL-038)."""
    escritorio = Escritorio.objects.create(nome="Escritório DL-086", cnpj="11222333000181")
    usuario = get_user_model().objects.create_user(
        username="cliente-dl086",
        email="cliente-dl086@escritorio.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.CLIENTE
    )
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Visível Ltda", cnpj="11122233000183"
    )
    return escritorio, empresa


def _kwargs_para(nomes_de_parametro, empresa_id):
    # Parâmetros que não são `empresa_id` recebem 1 — a guarda do papel roda
    # antes de qualquer outro parâmetro ser lido (mesma premissa da DL-038).
    return {nome: (empresa_id if nome == "empresa_id" else 1) for nome in nomes_de_parametro}


def _metodos_aceitos(client, endereco):
    """Sonda TRACE (padrão DL-038/DL-061): nenhuma rota deste conjunto
    implementa TRACE, então o 405 devolve o `Allow` completo sem executar o
    handler."""
    resposta = client.generic("TRACE", endereco)
    allow = resposta.headers.get("Allow", "")
    metodos = {m.strip().upper() for m in allow.split(",") if m.strip()}
    return metodos - {"HEAD", "OPTIONS"}


def _corpo_normalizado(resposta):
    """Corpo comparável entre duas requisições: o token CSRF é mascarado a
    cada render (mesma sessão, valores diferentes), então ele não pode
    entrar na comparação byte a byte."""
    texto = resposta.content.decode()
    # O token CSRF do Django tem 64 caracteres alfanuméricos; mascarar todo
    # bloco desse tamanho é independente da ordem dos atributos do input.
    return re.sub(r"[A-Za-z0-9_-]{64}", "TOKEN", texto)


@pytest.mark.parametrize("rota,nomes_de_parametro", ROTAS_WEB, ids=[r[0] for r in ROTAS_WEB])
def test_cliente_recebe_a_mesma_resposta_para_empresa_existente_e_inexistente(
    client, cenario_cliente, rota, nomes_de_parametro
):
    assert not Empresa.objects.filter(pk=ID_INEXISTENTE).exists()
    escritorio, empresa = cenario_cliente
    assert client.login(username="cliente-dl086", password="senha-forte-123")

    endereco_existente = reverse(rota, kwargs=_kwargs_para(nomes_de_parametro, empresa.pk))
    endereco_inexistente = reverse(rota, kwargs=_kwargs_para(nomes_de_parametro, ID_INEXISTENTE))

    metodos = _metodos_aceitos(client, endereco_existente)
    assert metodos, (rota, "nenhum método aceito detectado — sonda quebrada")

    for metodo in metodos:
        if metodo == "GET":
            existente = client.get(endereco_existente)
            inexistente = client.get(endereco_inexistente)
        elif metodo == "POST":
            existente = client.post(endereco_existente, data={})
            inexistente = client.post(endereco_inexistente, data={})
        else:
            continue

        # A MESMA resposta: status idêntico e corpo idêntico (normalizado).
        assert existente.status_code == inexistente.status_code, (rota, metodo)
        assert existente.status_code == 403, (
            rota,
            metodo,
            existente.status_code,
            inexistente.status_code,
        )
        assert _corpo_normalizado(existente) == _corpo_normalizado(inexistente), (rota, metodo)
        # E a recusa não vaza dado da empresa existente (B7 da DL-038: nem
        # razão social, nem modo de escrituração).
        corpo = existente.content.decode()
        assert empresa.razao_social not in corpo, (rota, metodo)
        if metodo == "POST":
            assert not Conta.objects.filter(empresa=empresa).exists(), (rota, metodo)
            assert not LancamentoContabil.objects.filter(empresa=empresa).exists(), (
                rota,
                metodo,
            )


def test_papel_que_le_com_id_inexistente_continua_recebendo_404(client, cenario_cliente):
    """Mutante "403 para todos": se a guarda do papel virasse recusa
    universal, o isolamento do critério 2 (empresa de outro escritório ou id
    inexistente = 404 para QUEM PODE LER) quebraria aqui."""
    escritorio, empresa = cenario_cliente
    leitor = get_user_model().objects.create_user(
        username="gestor-dl086", email="gestor-dl086@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=leitor, escritorio=escritorio, papel=Papel.GESTOR
    )
    assert client.login(username="gestor-dl086", password="senha-forte-123")

    endereco = reverse("contabilidade_web:plano_de_contas", kwargs={"empresa_id": ID_INEXISTENTE})
    resposta = client.get(endereco)
    assert resposta.status_code == 404


def test_papel_que_le_acessa_a_empresa_do_proprio_escritorio(client, cenario_cliente):
    """Par positivo do teste anterior: sem ele, uma guarda que devolvesse 404
    para TODO mundo também passaria nos dois testes de cima."""
    escritorio, empresa = cenario_cliente
    leitor = get_user_model().objects.create_user(
        username="gestor-dl086-ok",
        email="gestor-dl086-ok@escritorio.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=leitor, escritorio=escritorio, papel=Papel.GESTOR
    )
    assert client.login(username="gestor-dl086-ok", password="senha-forte-123")

    endereco = reverse("contabilidade_web:plano_de_contas", kwargs={"empresa_id": empresa.pk})
    resposta = client.get(endereco)
    assert resposta.status_code == 200
