"""DL-068, item 2 — o limite de tentativas da DL-056 também vale em `/admin/login/`.

Critérios de aceite do plano (docs/planos/DL-068, nível 1), numerados como lá:

2. Depois de N falhas na janela para o mesmo usuário, a tentativa seguinte é
   recusada MESMO com a senha correta de um superusuário, com a mesma resposta
   do login inválido; depois da janela (relógio controlado), a senha entra.
3. As falhas em `/login/` contam para `/admin/login/` e vice-versa.
4. O limite por IP vale no admin entre usuários diferentes.
5. O bloqueio no admin grava `login.bloqueado` só com o resumo do usuário, nunca
   o texto digitado nem a senha.
6. Usuário sem `is_staff` continua recusado no admin, com a senha correta e
   abaixo do limite.

N e o limite por IP vêm de `settings`, não de números escritos aqui: o teste
acompanha o valor configurado em vez de congelar o 5 e o 20 da DL-056.

O relógio é controlado por `limite_tentativas._agora` (mesmo padrão da DL-056);
todos os dados são sintéticos.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from django.contrib import admin
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth import get_user_model
from django.core import serializers
from django.test import Client
from django.urls import reverse

from apps.accounts import limite_tentativas
from apps.accounts.forms import AdminLoginForm, LoginForm
from apps.accounts.models import TentativaDeAcesso
from apps.auditoria.models import RegistroAuditoria

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"
IP_A = "203.0.113.10"
IP_B = "203.0.113.20"
T0 = datetime(2026, 10, 7, 12, 0, 0, tzinfo=timezone.utc)


class Relogio:
    """Relógio manual: o tempo só anda quando o teste manda."""

    def __init__(self):
        self.agora = T0

    def __call__(self):
        return self.agora

    def avancar(self, **kwargs):
        self.agora += timedelta(**kwargs)


@pytest.fixture
def relogio(monkeypatch):
    r = Relogio()
    monkeypatch.setattr(limite_tentativas, "_agora", r)
    return r


@pytest.fixture
def superusuario():
    return get_user_model().objects.create_superuser(
        username="chefe", email="chefe@escritorio.example", password=SENHA
    )


@pytest.fixture
def n_usuario(settings):
    return settings.LIMITE_TENTATIVAS_LOGIN_POR_USUARIO


@pytest.fixture
def n_ip(settings):
    return settings.LIMITE_TENTATIVAS_LOGIN_POR_IP


def _admin(usuario_digitado, senha, ip=IP_A, client=None):
    # `next` é o campo oculto que o template do admin renderiza (valor
    # `/admin/`); sem ele o Django redireciona para `LOGIN_REDIRECT_URL`.
    return (client or Client()).post(
        reverse("admin:login"),
        {"username": usuario_digitado, "password": senha, "next": reverse("admin:index")},
        REMOTE_ADDR=ip,
    )


def _login(usuario_digitado, senha, ip=IP_A, client=None):
    return (client or Client()).post(
        reverse("login"),
        {"username": usuario_digitado, "password": senha},
        REMOTE_ADDR=ip,
    )


def _entrou(resposta):
    return resposta.status_code == 302


def _mensagem(resposta):
    return [str(e) for e in resposta.context["form"].non_field_errors()]


def _falhar_no_admin(usuario_digitado, vezes, ip=IP_A):
    for _ in range(vezes):
        assert not _entrou(_admin(usuario_digitado, "senha-errada", ip=ip))


def _falhar_no_login(usuario_digitado, vezes, ip=IP_A):
    for _ in range(vezes):
        assert not _entrou(_login(usuario_digitado, "senha-errada", ip=ip))


# --- A ligação do formulário ao admin ------------------------------------------


def test_o_admin_usa_o_formulario_com_limite():
    assert admin.site.login_form is AdminLoginForm


def test_ordem_de_heranca_do_formulario_do_admin():
    # A ordem é o que faz o `clean()` com limite (LoginForm) rodar ANTES do
    # `AuthenticationForm.clean`, e ainda assim valer o `is_staff` do admin.
    mro = AdminLoginForm.__mro__
    assert mro.index(LoginForm) < mro.index(AdminAuthenticationForm)
    assert AdminLoginForm.clean is LoginForm.clean
    assert AdminLoginForm.confirm_login_allowed is AdminAuthenticationForm.confirm_login_allowed
    assert AdminLoginForm.error_messages is AdminAuthenticationForm.error_messages


# --- Critério 2 ----------------------------------------------------------------


def test_n_falhas_no_admin_bloqueiam_ate_a_janela_passar_mesmo_com_senha_certa(
    relogio, superusuario, n_usuario, settings
):
    baseline = _admin("fantasma", "senha-errada", ip=IP_B)  # login inválido sem bloqueio
    assert baseline.status_code == 200
    assert _mensagem(baseline), "a mensagem do login inválido do admin precisa existir"

    _falhar_no_admin("chefe", n_usuario)

    # Tentativa N+1, com a senha CERTA: recusada, sem sessão, e igual ao login
    # inválido (mesmo status e mesma mensagem — não diz que há bloqueio).
    client = Client()
    bloqueada = _admin("chefe", SENHA, client=client)
    assert bloqueada.status_code == baseline.status_code
    assert _mensagem(bloqueada) == _mensagem(baseline)
    assert "_auth_user_id" not in client.session

    # Um segundo antes de fechar a janela ainda está bloqueado — e a tentativa
    # bloqueada acima não pode ter renovado o bloqueio.
    janela = settings.LIMITE_TENTATIVAS_LOGIN_JANELA_SEGUNDOS
    relogio.avancar(seconds=janela - 1)
    assert not _entrou(_admin("chefe", SENHA))

    relogio.avancar(seconds=2)
    client = Client()
    entrou = _admin("chefe", SENHA, client=client)
    assert entrou.status_code == 302
    assert entrou["Location"] == reverse("admin:index")
    assert "_auth_user_id" in client.session


def test_limite_exato_n_menos_1_falhas_entra_e_n_falhas_recusa(relogio, superusuario, n_usuario):
    _falhar_no_admin("chefe", n_usuario - 1)
    client = Client()
    assert _entrou(_admin("chefe", SENHA, client=client))
    assert "_auth_user_id" in client.session

    # Segundo cenário, limpo: N falhas e a senha certa é recusada.
    TentativaDeAcesso.objects.all().delete()
    _falhar_no_admin("chefe", n_usuario)
    client = Client()
    assert not _entrou(_admin("chefe", SENHA, client=client))
    assert "_auth_user_id" not in client.session


def test_bloqueio_no_admin_tem_a_mesma_resposta_para_usuario_existente_e_inexistente(
    relogio, superusuario, n_usuario
):
    baseline = _admin("fantasma", "senha-errada", ip=IP_B)
    _falhar_no_admin("chefe", n_usuario)
    _falhar_no_admin("fantasma", n_usuario)

    bloqueada_existente = _admin("chefe", SENHA)
    bloqueada_inexistente = _admin("fantasma", SENHA)

    for resposta in (bloqueada_existente, bloqueada_inexistente):
        assert resposta.status_code == baseline.status_code
        assert _mensagem(resposta) == _mensagem(baseline)


# --- Critério 3: contagem compartilhada entre /login/ e /admin/login/ -------------


def test_falhas_em_login_bloqueiam_o_admin(relogio, superusuario, n_usuario):
    _falhar_no_login("chefe", n_usuario)

    client = Client()
    assert not _entrou(_admin("chefe", SENHA, client=client))
    assert "_auth_user_id" not in client.session


def test_falhas_no_admin_bloqueiam_o_login(relogio, superusuario, n_usuario):
    _falhar_no_admin("chefe", n_usuario)

    client = Client()
    assert not _entrou(_login("chefe", SENHA, client=client))
    assert "_auth_user_id" not in client.session


def test_a_contagem_soma_as_duas_portas(relogio, superusuario, n_usuario):
    # N-1 falhas divididas entre as duas portas ainda deixam entrar; uma contagem
    # separada por porta nunca chegaria perto de N em nenhuma delas.
    metade = (n_usuario - 1) // 2
    _falhar_no_login("chefe", metade)
    _falhar_no_admin("chefe", n_usuario - 1 - metade)
    assert TentativaDeAcesso.objects.filter(escopo="login_usuario").count() == n_usuario - 1

    # A N-ésima falha, em qualquer porta, fecha as duas.
    _falhar_no_login("chefe", 1)
    assert not _entrou(_admin("chefe", SENHA))
    assert not _entrou(_login("chefe", SENHA))


def test_limite_por_ip_e_compartilhado_entre_as_portas(relogio, superusuario, n_ip):
    for i in range(n_ip):
        assert not _entrou(_login(f"alvo-{i}", "senha-errada", ip=IP_A))
    assert not _entrou(_admin("chefe", SENHA, ip=IP_A))

    TentativaDeAcesso.objects.all().delete()
    for i in range(n_ip):
        assert not _entrou(_admin(f"alvo-{i}", "senha-errada", ip=IP_A))
    assert not _entrou(_login("chefe", SENHA, ip=IP_A))


def test_o_bloqueio_de_um_usuario_no_admin_nao_barra_outro(relogio, superusuario, n_usuario):
    get_user_model().objects.create_superuser(
        username="outro", email="outro@escritorio.example", password=SENHA
    )
    _falhar_no_admin("chefe", n_usuario)
    assert _entrou(_admin("outro", SENHA))


# --- Critério 4: limite por IP no admin --------------------------------------------


def test_limite_por_ip_vale_no_admin_entre_usuarios_diferentes(
    relogio, superusuario, n_ip, settings
):
    # n_ip falhas do mesmo IP, cada uma contra um usuário diferente (nenhum deles
    # chega ao limite por usuário).
    for i in range(n_ip):
        assert not _entrou(_admin(f"alvo-{i}", "senha-errada", ip=IP_A))

    # Outro usuário, senha certa, mesmo IP: bloqueado. Outro IP não é afetado.
    assert not _entrou(_admin("chefe", SENHA, ip=IP_A))
    assert _entrou(_admin("chefe", SENHA, ip=IP_B))

    relogio.avancar(seconds=settings.LIMITE_TENTATIVAS_LOGIN_JANELA_SEGUNDOS + 1)
    assert _entrou(_admin("chefe", SENHA, ip=IP_A))


def test_limite_por_ip_no_admin_n_menos_1_falhas_ainda_entra(relogio, superusuario, n_ip):
    for i in range(n_ip - 1):
        assert not _entrou(_admin(f"alvo-{i}", "senha-errada", ip=IP_A))
    assert _entrou(_admin("chefe", SENHA, ip=IP_A))


# --- Critério 5: trilha, sem texto digitado nem senha ---------------------------------


def test_bloqueio_no_admin_grava_login_bloqueado_sem_usuario_nem_senha(relogio, n_usuario):
    # O usuário digitado é uma conta REAL (staff) e as senhas são marcadoras:
    # se qualquer um vazasse para o registro, a busca abaixo o acharia.
    usuario_marcador = "marcador-usuario-dl068"
    senha_certa = "marcador-senha-certa-dl068"
    senha_errada = "marcador-senha-errada-dl068"
    get_user_model().objects.create_superuser(
        username=usuario_marcador, email="marcador@escritorio.example", password=senha_certa
    )
    for _ in range(n_usuario):
        _admin(usuario_marcador, senha_errada)
    antes = RegistroAuditoria.objects.filter(acao="login.bloqueado").count()
    assert antes == 0, "falhas abaixo do limite não são bloqueio"

    _admin(usuario_marcador, senha_certa)  # bloqueada

    registro = RegistroAuditoria.objects.get(acao="login.bloqueado")
    assert registro.endereco_ip == IP_A
    assert registro.detalhes["motivo"] == "usuario"
    assert registro.detalhes["usuario_hash"]
    # O registro INTEIRO serializado (todas as colunas, não só `detalhes`).
    todo_o_registro = json.dumps(
        json.loads(serializers.serialize("json", [registro])), ensure_ascii=False
    )
    for proibido in (usuario_marcador, senha_certa, senha_errada):
        assert proibido not in todo_o_registro
    # O resumo é o mesmo valor que o limitador usa para correlacionar a tentativa.
    assert registro.detalhes["usuario_hash"] == limite_tentativas.resumo_do_usuario(
        usuario_marcador
    )
    # Nem o contador guarda o texto digitado.
    for linha in TentativaDeAcesso.objects.all():
        assert usuario_marcador not in linha.chave
        assert senha_certa not in linha.chave


def test_bloqueio_por_ip_no_admin_registra_motivo_ip(relogio, superusuario, n_ip):
    for i in range(n_ip):
        _admin(f"alvo-{i}", "senha-errada")
    _admin("chefe", SENHA)
    assert RegistroAuditoria.objects.get(acao="login.bloqueado").detalhes["motivo"] == "ip"


# --- Critério 6: is_staff continua valendo ------------------------------------------


def test_usuario_sem_is_staff_com_senha_certa_continua_recusado_no_admin(relogio):
    get_user_model().objects.create_user(
        username="comum", email="comum@escritorio.example", password=SENHA
    )
    baseline = _admin("fantasma", "senha-errada", ip=IP_B)

    client = Client()
    resposta = _admin("comum", SENHA, client=client)

    assert resposta.status_code == 200
    assert _mensagem(resposta) == _mensagem(baseline)
    assert "_auth_user_id" not in client.session
    # A recusa por não ser staff conta como falha, para que a porta do admin não
    # sirva de oráculo de "senha certa" sem custo.
    assert (
        TentativaDeAcesso.objects.filter(
            escopo="login_usuario", chave=limite_tentativas.chave_do_usuario("comum")
        ).count()
        == 1
    )


def test_usuario_sem_is_staff_continua_entrando_em_login_normal(relogio):
    # O `is_staff` é exigência do ADMIN, não do `/login/`: o formulário novo não
    # pode vazar para a outra porta.
    get_user_model().objects.create_user(
        username="comum", email="comum@escritorio.example", password=SENHA
    )
    client = Client()
    assert _entrou(_login("comum", SENHA, client=client))
    assert "_auth_user_id" in client.session


def test_superusuario_abaixo_do_limite_entra_no_admin(relogio, superusuario, n_usuario):
    # Sucesso: o limite não atrapalha quem erra algumas vezes e acerta.
    _falhar_no_admin("chefe", n_usuario - 1)
    client = Client()
    resposta = _admin("chefe", SENHA, client=client)
    assert resposta.status_code == 302
    assert client.get(reverse("admin:index")).status_code == 200
