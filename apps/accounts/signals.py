import hashlib
import hmac
import unicodedata

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from apps.auditoria.services import registrar


@receiver(user_logged_in)
def registrar_login_sucesso(sender, request, user, **kwargs):
    registrar(acao="login.sucesso", usuario=user, request=request)


@receiver(user_logged_out)
def registrar_logout(sender, request, user, **kwargs):
    registrar(acao="logout", usuario=user, request=request)


def _prefixo_hmac_do_texto_digitado(texto):
    """Prefixo (16 hex) do HMAC-SHA256 do texto normalizado.

    DL-058/B3. Normaliza com NFKC + strip + casefold e assina com a
    `SECRET_KEY`: o suficiente para reconhecer a MESMA tentativa repetida
    (detectar força bruta contra um alvo) sem gravar o texto, que pode ser
    uma senha digitada no campo errado. O HMAC com segredo impede que quem
    leia a trilha teste candidatos offline.

    TODO(DL-058/integração): a DL-056 criou um hash equivalente em
    `apps/accounts/limite_tentativas.py`, ainda não integrado a esta
    branch. Esta é uma cópia local deliberada; ao integrar, UNIFICAR em uma
    única função para que a trilha e o limitador usem o mesmo valor.
    """
    normalizado = unicodedata.normalize("NFKC", str(texto)).strip().casefold()
    assinatura = hmac.new(
        settings.SECRET_KEY.encode("utf-8"), normalizado.encode("utf-8"), hashlib.sha256
    )
    return assinatura.hexdigest()[:16]


@receiver(user_login_failed)
def registrar_login_falha(sender, credentials, request=None, **kwargs):
    # Nunca gravar a senha. DL-058/B3: o campo "usuário" também não vai
    # cru para a trilha quando não corresponde a uma conta — quem digita a
    # senha no campo errado a colocaria na trilha de auditoria, em claro.
    # Conta existente: grava o nome (já é dado da própria conta, útil para
    # detectar tentativas repetidas contra ela). Conta inexistente: grava
    # só o prefixo do HMAC, que ainda permite agrupar a mesma tentativa.
    digitado = str(credentials.get("username", "") or "")
    conta_existe = (
        bool(digitado)
        and get_user_model()._default_manager.filter(username__iexact=digitado).exists()
    )
    if conta_existe:
        detalhes = {"username": digitado}
    else:
        detalhes = {"username_hmac": _prefixo_hmac_do_texto_digitado(digitado)}
    registrar(acao="login.falha", request=request, detalhes=detalhes)
