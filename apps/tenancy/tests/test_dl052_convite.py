"""DL-052 (A2) — o convite de escritório vence em 7 dias e só vale para o
e-mail convidado.

Antes desta etapa `aceitar_convite_e_criar_vinculo` não consultava
`ConviteEscritorio.expirado` nem o e-mail: um convite de 400 dias era aceito
por qualquer usuário autenticado, com qualquer e-mail, e o token (que viaja
na URL) valia como chave de entrada para sempre.

Critérios de aceite do plano cobertos aqui:

1. Convite com mais de 7 dias é recusado, sem vínculo e sem consumir o
   convite; 7 dias menos um segundo é aceito (limite).
2. E-mail diferente é recusado, sem vínculo; o mesmo e-mail com
   maiúsculas/espaços diferentes é aceito.

O relógio é controlado por `patch("django.utils.timezone.now")`: tanto
`ConviteEscritorio.expirado` quanto o serviço chamam `timezone.now()` pelo
módulo, então um único patch vale para os dois. Dados sintéticos.
"""

from datetime import datetime, timedelta
from datetime import timezone as fuso
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.auditoria.models import RegistroAuditoria
from apps.tenancy.models import (
    ConviteEscritorio,
    Escritorio,
    Papel,
    VinculoUsuarioEscritorio,
)
from apps.tenancy.services.primeiro_acesso import (
    ConviteInvalido,
    aceitar_convite_e_criar_vinculo,
    emitir_convite_para_escritorio,
)

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"
EMISSAO = datetime(2026, 3, 2, 12, 0, 0, tzinfo=fuso.utc)
SETE_DIAS = timedelta(days=7)


@pytest.fixture
def cenario():
    User = get_user_model()
    escritorio = Escritorio.objects.create(nome="Escritório Convite 052", cnpj="10101010000110")
    admin = User.objects.create_user(username="admin052", email="admin@dl052.local", password=SENHA)
    VinculoUsuarioEscritorio.objects.create(
        usuario=admin, escritorio=escritorio, papel=Papel.ADMINISTRADOR, ativo=True
    )
    convite = emitir_convite_para_escritorio(
        escritorio=escritorio, email_convidado="Convidada@DL052.local", convidador=admin
    )
    # `criado_em` é auto_now_add: fixa a emissão num instante conhecido.
    ConviteEscritorio.objects.filter(pk=convite.pk).update(criado_em=EMISSAO)
    convite.refresh_from_db()
    convidada = User.objects.create_user(
        username="convidada052", email="convidada@dl052.local", password=SENHA
    )
    return {"escritorio": escritorio, "convite": convite, "convidada": convidada}


def _agora(instante):
    return patch("django.utils.timezone.now", return_value=instante)


def _sem_vinculo(escritorio, usuario):
    return not VinculoUsuarioEscritorio.objects.filter(
        usuario=usuario, escritorio=escritorio
    ).exists()


# --- critério 1: prazo ------------------------------------------------------


def test_convite_de_400_dias_e_recusado_sem_vinculo_e_sem_consumir(cenario):
    convite, convidada = cenario["convite"], cenario["convidada"]

    with _agora(EMISSAO + timedelta(days=400)):
        with pytest.raises(ConviteInvalido) as erro:
            aceitar_convite_e_criar_vinculo(token=convite.token, usuario=convidada)

    assert "venceu" in str(erro.value)
    assert _sem_vinculo(cenario["escritorio"], convidada)
    convite.refresh_from_db()
    assert convite.consumido_em is None
    assert convite.consumido_por is None


def test_limite_sete_dias_mais_um_segundo_e_recusado(cenario):
    convite, convidada = cenario["convite"], cenario["convidada"]

    with _agora(EMISSAO + SETE_DIAS + timedelta(seconds=1)):
        with pytest.raises(ConviteInvalido):
            aceitar_convite_e_criar_vinculo(token=convite.token, usuario=convidada)

    assert _sem_vinculo(cenario["escritorio"], convidada)
    convite.refresh_from_db()
    assert convite.consumido_em is None


def test_limite_sete_dias_menos_um_segundo_e_aceito(cenario):
    convite, convidada = cenario["convite"], cenario["convidada"]

    with _agora(EMISSAO + SETE_DIAS - timedelta(seconds=1)):
        resultado = aceitar_convite_e_criar_vinculo(token=convite.token, usuario=convidada)

    assert resultado.vinculo.usuario == convidada
    assert resultado.vinculo.papel == Papel.ANALISTA
    convite.refresh_from_db()
    assert convite.consumido_por == convidada


def test_limite_exatamente_sete_dias_ainda_vale_fronteira_estrita(cenario):
    """`expirado` usa `>`: no instante exato `criado_em + 7 dias` o convite
    ainda é aceito; é a fronteira documentada em `ConviteEscritorio.expirado`."""
    convite, convidada = cenario["convite"], cenario["convidada"]

    with _agora(EMISSAO + SETE_DIAS):
        resultado = aceitar_convite_e_criar_vinculo(token=convite.token, usuario=convidada)

    assert resultado.vinculo.ativo is True


# --- critério 2: e-mail -----------------------------------------------------


def test_usuario_com_outro_email_e_recusado_sem_vinculo(cenario):
    convite = cenario["convite"]
    intruso = get_user_model().objects.create_user(
        username="intruso052", email="intruso@dl052.local", password=SENHA
    )

    with _agora(EMISSAO + timedelta(days=1)):
        with pytest.raises(ConviteInvalido) as erro:
            aceitar_convite_e_criar_vinculo(token=convite.token, usuario=intruso)

    assert _sem_vinculo(cenario["escritorio"], intruso)
    convite.refresh_from_db()
    assert convite.consumido_em is None
    # Não revela a qual e-mail o convite pertence.
    assert "dl052.local" not in str(erro.value)
    assert "convidada" not in str(erro.value).lower()


def test_usuario_sem_email_e_recusado(cenario):
    convite = cenario["convite"]
    sem_email = get_user_model().objects.create_user(
        username="sememail052", email="", password=SENHA
    )

    with _agora(EMISSAO + timedelta(days=1)):
        with pytest.raises(ConviteInvalido):
            aceitar_convite_e_criar_vinculo(token=convite.token, usuario=sem_email)

    assert _sem_vinculo(cenario["escritorio"], sem_email)


def test_mesmo_email_com_maiusculas_e_espacos_diferentes_e_aceito(cenario):
    """O convite foi emitido para `Convidada@DL052.local`; o usuário tem
    `  CONVIDADA@dl052.LOCAL ` — mesmo endereço, só a forma difere."""
    convite = cenario["convite"]
    outra_grafia = get_user_model().objects.create_user(
        username="grafia052", email="  CONVIDADA@dl052.LOCAL ", password=SENHA
    )

    with _agora(EMISSAO + timedelta(days=1)):
        resultado = aceitar_convite_e_criar_vinculo(token=convite.token, usuario=outra_grafia)

    assert resultado.vinculo.usuario == outra_grafia
    convite.refresh_from_db()
    assert convite.consumido_por == outra_grafia


def test_recusa_nao_grava_trilha_de_aceite(cenario):
    convite, convidada = cenario["convite"], cenario["convidada"]

    with _agora(EMISSAO + timedelta(days=30)):
        with pytest.raises(ConviteInvalido):
            aceitar_convite_e_criar_vinculo(token=convite.token, usuario=convidada)

    assert not RegistroAuditoria.objects.filter(acao="convite.escritorio.aceito").exists()


# --- telas ------------------------------------------------------------------
# Nas telas o relógio NÃO é adiantado: o cookie de sessão também vence pelo
# `timezone.now()`, e um relógio 400 dias à frente deslogaria o usuário antes
# de a view rodar. Em vez disso recua-se a emissão do convite.


def _emitido_ha(convite, intervalo):
    ConviteEscritorio.objects.filter(pk=convite.pk).update(criado_em=timezone.now() - intervalo)


def test_tela_informa_que_o_convite_venceu_e_nao_oferece_aceitar(client, cenario):
    convite = cenario["convite"]
    _emitido_ha(convite, timedelta(days=8))
    client.force_login(cenario["convidada"])

    resposta = client.get(reverse("tenancy:aceitar-convite", kwargs={"token": convite.token}))

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "venceu" in html
    assert "Aceitar e entrar" not in html


def test_tela_avisa_email_diferente_sem_revelar_o_email_do_convite(client, cenario):
    convite = cenario["convite"]
    _emitido_ha(convite, timedelta(days=1))
    intruso = get_user_model().objects.create_user(
        username="intruso-tela052", email="intruso-tela@dl052.local", password=SENHA
    )
    client.force_login(intruso)

    resposta = client.get(reverse("tenancy:aceitar-convite", kwargs={"token": convite.token}))

    html = resposta.content.decode()
    assert "não foi emitido para o e-mail da sua conta" in html
    assert "Aceitar e entrar" not in html
    assert "convidada@dl052.local" not in html.lower()


def test_tela_oferece_aceitar_quando_no_prazo_e_com_o_email_certo(client, cenario):
    convite = cenario["convite"]
    _emitido_ha(convite, timedelta(days=1))
    client.force_login(cenario["convidada"])

    resposta = client.get(reverse("tenancy:aceitar-convite", kwargs={"token": convite.token}))

    assert "Aceitar e entrar" in resposta.content.decode()


def test_post_na_view_com_convite_vencido_nao_cria_vinculo_e_informa(client, cenario):
    convite, convidada = cenario["convite"], cenario["convidada"]
    _emitido_ha(convite, timedelta(days=400))
    client.force_login(convidada)

    resposta = client.post(
        reverse("tenancy:aceitar-convite", kwargs={"token": convite.token}), follow=True
    )

    assert resposta.status_code == 200
    mensagens = [str(m) for m in resposta.context["messages"]]
    assert any("venceu" in m for m in mensagens)
    assert _sem_vinculo(cenario["escritorio"], convidada)
    convite.refresh_from_db()
    assert convite.consumido_em is None


def test_post_na_view_com_email_diferente_nao_cria_vinculo(client, cenario):
    convite = cenario["convite"]
    _emitido_ha(convite, timedelta(days=1))
    intruso = get_user_model().objects.create_user(
        username="intruso-post052", email="intruso-post@dl052.local", password=SENHA
    )
    client.force_login(intruso)

    resposta = client.post(
        reverse("tenancy:aceitar-convite", kwargs={"token": convite.token}), follow=True
    )

    mensagens = [str(m) for m in resposta.context["messages"]]
    assert any("não foi emitido para o e-mail da sua conta" in m for m in mensagens)
    assert _sem_vinculo(cenario["escritorio"], intruso)
    convite.refresh_from_db()
    assert convite.consumido_em is None


# --- rodada 1, D5: quem já está vinculado ao escritório ----------------------


def _convite_para_o_admin(cenario):
    """O administrador convida o próprio e-mail: já tem vínculo com o escritório."""
    admin = VinculoUsuarioEscritorio.objects.get(
        escritorio=cenario["escritorio"], papel=Papel.ADMINISTRADOR
    ).usuario
    convite = cenario["convite"]
    ConviteEscritorio.objects.filter(pk=convite.pk).update(
        email=admin.email, criado_em=timezone.now() - timedelta(days=1)
    )
    convite.refresh_from_db()
    return admin, convite


def test_usuario_ja_vinculado_ao_escritorio_e_recusado_sem_500_e_sem_consumir(cenario):
    admin, convite = _convite_para_o_admin(cenario)

    with pytest.raises(ConviteInvalido) as erro:
        aceitar_convite_e_criar_vinculo(token=convite.token, usuario=admin)

    assert "já tem vínculo" in str(erro.value)
    assert VinculoUsuarioEscritorio.objects.filter(usuario=admin).count() == 1
    convite.refresh_from_db()
    assert convite.consumido_em is None


def test_usuario_com_vinculo_inativo_tambem_e_recusado_sem_500(cenario):
    admin, convite = _convite_para_o_admin(cenario)
    VinculoUsuarioEscritorio.objects.filter(usuario=admin).update(ativo=False)

    with pytest.raises(ConviteInvalido):
        aceitar_convite_e_criar_vinculo(token=convite.token, usuario=admin)

    convite.refresh_from_db()
    assert convite.consumido_em is None


def test_view_com_usuario_ja_vinculado_responde_302_com_mensagem(client, cenario):
    admin, convite = _convite_para_o_admin(cenario)
    client.force_login(admin)

    resposta = client.post(
        reverse("tenancy:aceitar-convite", kwargs={"token": convite.token}), follow=True
    )

    assert resposta.redirect_chain and resposta.redirect_chain[0][1] == 302
    assert any("já tem vínculo" in str(m) for m in resposta.context["messages"])
    convite.refresh_from_db()
    assert convite.consumido_em is None
