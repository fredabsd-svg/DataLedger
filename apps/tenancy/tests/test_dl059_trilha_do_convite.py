"""DL-059 — trilha do convite e eventos de tenancy com a origem (IP).

Cobre, do plano `docs/planos/DL-059-trilha-do-convite-e-eventos-sem-ip.md`:

1. (BL-566) recusa de convite vencido, de e-mail divergente ou de usuário já
   vinculado grava exatamente um evento `convite.escritorio.recusado`, com
   `convite_id` e `motivo`, sem e-mail; nenhum vínculo; convite não consumido;
   o evento SOBREVIVE ao rollback da transação do aceite.
2. (BL-560) a tela do convite já consumido explica e não oferece "Aceitar";
   o POST continua recusado.
3. (BL-579) os eventos de tenancy que não gravavam IP (ativar escritório, na
   API e na tela; primeiro acesso; convite emitido; convite aceito) gravam o
   `REMOTE_ADDR` da requisição; chamada de serviço sem request continua
   funcionando (sem IP).

Dados sintéticos; IPs de documentação (RFC 5737).
"""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
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
    MOTIVO_EMAIL_DIVERGENTE,
    MOTIVO_JA_VINCULADO,
    MOTIVO_VENCIDO,
    ConviteInvalido,
    aceitar_convite_e_criar_vinculo,
    criar_primeiro_escritorio_e_vinculo_admin,
    emitir_convite_para_escritorio,
)

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"
IP = "198.51.100.7"
EMAIL_CONVITE = "convidada@dl059.local"
MOTIVOS = [MOTIVO_VENCIDO, MOTIVO_EMAIL_DIVERGENTE, MOTIVO_JA_VINCULADO]


@pytest.fixture(autouse=True)
def sem_proxy_confiavel(settings):
    # Sem proxy configurado, o IP gravado é o REMOTE_ADDR (DL-057).
    settings.PROXIES_CONFIAVEIS = []


@pytest.fixture
def cenario():
    User = get_user_model()
    escritorio = Escritorio.objects.create(nome="Escritório Convite 059", cnpj="10101010000159")
    admin = User.objects.create_user(username="admin059", email="admin@dl059.local", password=SENHA)
    VinculoUsuarioEscritorio.objects.create(
        usuario=admin, escritorio=escritorio, papel=Papel.ADMINISTRADOR, ativo=True
    )
    convite = emitir_convite_para_escritorio(
        escritorio=escritorio, email_convidado=EMAIL_CONVITE, convidador=admin
    )
    convidada = User.objects.create_user(
        username="convidada059", email=EMAIL_CONVITE, password=SENHA
    )
    return {"escritorio": escritorio, "admin": admin, "convite": convite, "convidada": convidada}


def _envelhecer(convite, dias):
    ConviteEscritorio.objects.filter(pk=convite.pk).update(
        criado_em=timezone.now() - timedelta(days=dias)
    )


def _aceitar_pela_tela(client, usuario, convite, **extra):
    client.force_login(usuario)
    return client.post(reverse("tenancy:aceitar-convite", kwargs={"token": convite.token}), **extra)


def _recusas():
    return RegistroAuditoria.objects.filter(acao="convite.escritorio.recusado")


def _montar_recusa(cenario, motivo):
    """Devolve o usuário que apresentará o token, já no estado da recusa."""
    User = get_user_model()
    if motivo == MOTIVO_VENCIDO:
        _envelhecer(cenario["convite"], dias=8)
        return cenario["convidada"]
    if motivo == MOTIVO_EMAIL_DIVERGENTE:
        return User.objects.create_user(
            username="intruso059", email="intruso@dl059.local", password=SENHA
        )
    # ja_vinculado: o convidado já tem vínculo (inativo também conta) com o escritório.
    VinculoUsuarioEscritorio.objects.create(
        usuario=cenario["convidada"],
        escritorio=cenario["escritorio"],
        papel=Papel.ANALISTA,
        ativo=False,
    )
    return cenario["convidada"]


# --- item 1 (BL-566): recusa na trilha ---------------------------------------


@pytest.mark.parametrize("motivo", MOTIVOS)
def test_servico_recusa_grava_um_evento_com_motivo_e_sem_email(cenario, motivo):
    usuario = _montar_recusa(cenario, motivo)
    convite = cenario["convite"]
    vinculos_antes = VinculoUsuarioEscritorio.objects.count()

    with pytest.raises(ConviteInvalido) as erro:
        aceitar_convite_e_criar_vinculo(token=convite.token, usuario=usuario)

    # O motivo vem em atributo estruturado, não do texto da mensagem.
    assert erro.value.motivo == motivo
    eventos = list(_recusas())
    assert len(eventos) == 1
    evento = eventos[0]
    assert evento.detalhes == {"convite_id": convite.id, "motivo": motivo}
    assert evento.usuario == usuario
    assert evento.escritorio == cenario["escritorio"]
    # Sem e-mail de ninguém (nem do convite, nem de quem apresentou o token).
    texto = str(evento.detalhes) + evento.objeto_id + evento.objeto_tipo
    assert EMAIL_CONVITE not in texto and "intruso@dl059.local" not in texto
    assert convite.token not in texto
    # Nenhum vínculo criado, convite não consumido, nenhum evento de aceite.
    assert VinculoUsuarioEscritorio.objects.count() == vinculos_antes
    convite.refresh_from_db()
    assert convite.consumido_em is None and convite.consumido_por is None
    assert not RegistroAuditoria.objects.filter(acao="convite.escritorio.aceito").exists()


@pytest.mark.parametrize("motivo", MOTIVOS)
def test_tela_recusa_grava_o_evento_com_o_ip_da_requisicao(client, cenario, motivo):
    usuario = _montar_recusa(cenario, motivo)

    resposta = _aceitar_pela_tela(client, usuario, cenario["convite"], REMOTE_ADDR=IP)

    assert resposta.status_code == 302
    (evento,) = _recusas()
    assert evento.detalhes["motivo"] == motivo
    assert evento.endereco_ip == IP


def test_token_inexistente_e_token_consumido_nao_geram_evento_de_recusa(cenario):
    # Sem convite a apontar, não há `convite_id` nem motivo: nada é gravado
    # (e o token apresentado nunca vai para a trilha).
    with pytest.raises(ConviteInvalido) as erro:
        aceitar_convite_e_criar_vinculo(token="nao-existe-059", usuario=cenario["convidada"])
    assert erro.value.motivo is None

    aceitar_convite_e_criar_vinculo(token=cenario["convite"].token, usuario=cenario["convidada"])
    with pytest.raises(ConviteInvalido):
        aceitar_convite_e_criar_vinculo(
            token=cenario["convite"].token, usuario=cenario["convidada"]
        )

    assert not _recusas().exists()


@pytest.mark.django_db(transaction=True)
def test_evento_de_recusa_sobrevive_ao_rollback_da_transacao_do_aceite(cenario):
    """Com `transaction=True` não há transação de teste envolvendo tudo: o
    rollback da transação do aceite é REAL e o evento precisa estar no banco
    depois dele (lido por conexão nova)."""
    _envelhecer(cenario["convite"], dias=8)

    with pytest.raises(ConviteInvalido):
        aceitar_convite_e_criar_vinculo(
            token=cenario["convite"].token, usuario=cenario["convidada"]
        )

    connection.close()  # a leitura abaixo usa uma conexão nova
    assert _recusas().count() == 1


def test_aceite_valido_nao_grava_recusa_e_grava_o_aceite(cenario):
    aceitar_convite_e_criar_vinculo(token=cenario["convite"].token, usuario=cenario["convidada"])

    assert not _recusas().exists()
    assert RegistroAuditoria.objects.filter(acao="convite.escritorio.aceito").count() == 1


# --- item 2 (BL-560): convite consumido --------------------------------------


def test_tela_do_convite_consumido_explica_e_nao_oferece_aceitar(client, cenario):
    aceitar_convite_e_criar_vinculo(token=cenario["convite"].token, usuario=cenario["convidada"])
    client.force_login(cenario["convidada"])

    resposta = client.get(
        reverse("tenancy:aceitar-convite", kwargs={"token": cenario["convite"].token})
    )

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "já foi usado" in html
    assert "Aceitar e entrar" not in html
    # Não revela o e-mail do convite.
    assert EMAIL_CONVITE not in html


def test_tela_de_token_inexistente_diz_invalido_e_nao_oferece_aceitar(client, cenario):
    # BL-600: o ramo `not convite` só ocorre com token que não existe; não pode
    # usar o texto de expirado/consumido nem oferecer o botão de aceitar.
    client.force_login(cenario["convidada"])

    resposta = client.get(reverse("tenancy:aceitar-convite", kwargs={"token": "nao-existe"}))

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "inexistente ou inválido" in html
    assert "consumido" not in html
    assert "Aceitar e entrar" not in html


def test_post_do_convite_consumido_continua_recusado(client, cenario):
    aceitar_convite_e_criar_vinculo(token=cenario["convite"].token, usuario=cenario["convidada"])
    vinculos = VinculoUsuarioEscritorio.objects.count()

    resposta = _aceitar_pela_tela(client, cenario["convidada"], cenario["convite"])

    assert resposta.status_code == 302
    assert VinculoUsuarioEscritorio.objects.count() == vinculos


def test_tela_do_convite_valido_continua_oferecendo_aceitar(client, cenario):
    client.force_login(cenario["convidada"])

    resposta = client.get(
        reverse("tenancy:aceitar-convite", kwargs={"token": cenario["convite"].token})
    )

    assert "Aceitar e entrar" in resposta.content.decode()


# --- item 3 (BL-579): IP nos eventos de tenancy ------------------------------


def _unico(acao):
    return RegistroAuditoria.objects.get(acao=acao)


def test_aceite_pela_tela_grava_o_ip(client, cenario):
    resposta = _aceitar_pela_tela(client, cenario["convidada"], cenario["convite"], REMOTE_ADDR=IP)

    assert resposta.status_code == 302
    assert _unico("convite.escritorio.aceito").endereco_ip == IP


def test_aceite_atras_de_proxy_confiavel_grava_o_ip_do_cliente(client, cenario, settings):
    settings.PROXIES_CONFIAVEIS = ["203.0.113.1"]

    _aceitar_pela_tela(
        client,
        cenario["convidada"],
        cenario["convite"],
        REMOTE_ADDR="203.0.113.1",
        HTTP_X_FORWARDED_FOR=IP,
    )

    assert _unico("convite.escritorio.aceito").endereco_ip == IP


def test_convite_emitido_pela_tela_grava_o_ip(client, cenario):
    client.force_login(cenario["admin"])

    resposta = client.post(
        reverse("tenancy:emitir-convite"),
        {"escritorio_id": cenario["escritorio"].pk, "email": "outra@dl059.local"},
        REMOTE_ADDR=IP,
    )

    assert resposta.status_code == 302
    # O convite do cenário (emitido pelo serviço, sem request) também está na trilha.
    evento = RegistroAuditoria.objects.get(
        acao="convite.escritorio.emitido", detalhes__email_convidado="outra@dl059.local"
    )
    assert evento.endereco_ip == IP


def test_primeiro_acesso_pela_tela_grava_o_ip(client):
    usuario = get_user_model().objects.create_user(
        username="primeiro059", email="primeiro@dl059.local", password=SENHA
    )
    client.force_login(usuario)

    resposta = client.post(
        reverse("tenancy:bootstrap-primeiro-acesso"),
        {"nome": "Escritório Primeiro 059", "cnpj": "55555555000159"},
        REMOTE_ADDR=IP,
    )

    assert resposta.status_code == 302
    assert _unico("escritorio.criado_por_bootstrap").endereco_ip == IP


def test_ativar_escritorio_pela_tela_grava_o_ip(client, cenario):
    client.force_login(cenario["admin"])

    resposta = client.post(
        reverse("tenancy:ativar"), {"escritorio_id": cenario["escritorio"].pk}, REMOTE_ADDR=IP
    )

    assert resposta.status_code == 302
    assert _unico("escritorio.ativado").endereco_ip == IP


def test_ativar_escritorio_pela_api_grava_o_ip(client, cenario):
    client.force_login(cenario["admin"])

    resposta = client.post(
        reverse("tenancy:api-escritorio-ativo"),
        {"escritorio_id": cenario["escritorio"].pk},
        content_type="application/json",
        REMOTE_ADDR=IP,
    )

    assert resposta.status_code == 200
    assert _unico("escritorio.ativado").endereco_ip == IP


def test_servicos_sem_request_continuam_funcionando_sem_ip(cenario):
    # Compatibilidade: shell, importador e testes de serviço não têm request.
    novo = get_user_model().objects.create_user(
        username="semreq059", email="semreq@dl059.local", password=SENHA
    )

    criar_primeiro_escritorio_e_vinculo_admin(
        usuario=novo, nome="Sem Request", cnpj="66666666000159"
    )
    emitir_convite_para_escritorio(
        escritorio=cenario["escritorio"],
        email_convidado="x@dl059.local",
        convidador=cenario["admin"],
    )
    aceitar_convite_e_criar_vinculo(token=cenario["convite"].token, usuario=cenario["convidada"])

    for acao in (
        "escritorio.criado_por_bootstrap",
        "convite.escritorio.emitido",
        "convite.escritorio.aceito",
    ):
        assert RegistroAuditoria.objects.filter(acao=acao, endereco_ip__isnull=True).exists()
