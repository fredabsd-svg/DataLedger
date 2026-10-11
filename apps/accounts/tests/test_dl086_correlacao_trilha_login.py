"""DL-086 (BL-593) — `login.falha` e `login.bloqueado` se correlacionam.

O docstring de `resumo_do_usuario` (apps/accounts/limite_tentativas.py)
promete desde a DL-058 que o evento `login.falha`, o `login.bloqueado` e a
linha de `TentativaDeAcesso` "se correlacionam" pelo mesmo resumo HMAC. Na
prática a promessa não existia: `signals.py` gravava a chave
`username_hmac` e `forms.py` gravava `usuario_hash` — o mesmo valor sob dois
nomes, e nenhuma consulta de trilha consegue juntar os dois eventos sem
adivinhar. Critério de aceite do BL-593: "uma chave só, com teste de
correlação". A chave única é `username_hmac` (nome que diz o que o valor é:
HMAC, não hash simples; já era a usada pelos testes da trilha da DL-058).

O último teste é o controle de mutante: se a segunda chave voltar em
qualquer um dos dois eventos, ele reprova nomeando o evento.
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.accounts.limite_tentativas import resumo_do_usuario
from apps.auditoria.models import RegistroAuditoria

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"
IP = "203.0.113.77"


def _tentar(usuario_digitado, senha):
    return Client().post(
        reverse("login"), {"username": usuario_digitado, "password": senha}, REMOTE_ADDR=IP
    )


def test_conta_existente_falha_e_bloqueio_correlacionam_pelo_mesmo_resumo():
    get_user_model().objects.create_user(
        username="ana", email="ana@escritorio.example", password=SENHA
    )
    for _ in range(5):
        _tentar("ana", "senha-errada")
    _tentar("ana", SENHA)  # 6ª: bloqueada pelo limite do usuário

    falhas = list(RegistroAuditoria.objects.filter(acao="login.falha"))
    (bloqueio,) = RegistroAuditoria.objects.filter(acao="login.bloqueado")

    assert len(falhas) == 5
    # Conta existente: `login.falha` guarda o nome da conta (dado da própria
    # conta, DL-058/B3); a correlação com o bloqueio é pelo resumo do nome.
    for falha in falhas:
        assert falha.detalhes["username"] == "ana"
        assert resumo_do_usuario(falha.detalhes["username"]) == bloqueio.detalhes["username_hmac"]
    assert bloqueio.detalhes["motivo"] == "usuario"


def test_conta_inexistente_usa_a_mesma_chave_nos_dois_eventos():
    digitado = "fantasma-inexistente"
    for _ in range(5):
        _tentar(digitado, "senha-errada")
    _tentar(digitado, "senha-errada")  # 6ª: bloqueada

    falhas = list(RegistroAuditoria.objects.filter(acao="login.falha"))
    (bloqueio,) = RegistroAuditoria.objects.filter(acao="login.bloqueado")

    assert len(falhas) == 5
    esperado = resumo_do_usuario(digitado)
    for falha in falhas:
        assert falha.detalhes["username_hmac"] == esperado
    assert bloqueio.detalhes["username_hmac"] == esperado
    # O texto digitado nunca aparece em claro (regresso da DL-058/B3).
    for evento in [*falhas, bloqueio]:
        assert digitado not in str(evento.detalhes)


def test_a_chave_antiga_nao_volta_em_nenhum_evento():
    """Controle de mutante do BL-593: `usuario_hash` era a segunda chave; se
    ela reaparecer em qualquer um dos dois eventos, a correlação quebra de
    novo em silêncio — este teste reprova nomeando o evento."""
    _tentar("outra-inexistente", "senha-errada")
    for _ in range(5):
        _tentar("outra-inexistente", "senha-errada")

    for evento in RegistroAuditoria.objects.filter(acao__in=["login.falha", "login.bloqueado"]):
        assert "usuario_hash" not in evento.detalhes, (
            f"{evento.acao} voltou a gravar a segunda chave (BL-593)"
        )
