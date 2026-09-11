from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from apps.auditoria.services import registrar


@receiver(user_logged_in)
def registrar_login_sucesso(sender, request, user, **kwargs):
    registrar(acao="login.sucesso", usuario=user, request=request)


@receiver(user_logged_out)
def registrar_logout(sender, request, user, **kwargs):
    registrar(acao="logout", usuario=user, request=request)


@receiver(user_login_failed)
def registrar_login_falha(sender, credentials, request=None, **kwargs):
    # Nunca gravar a senha: só o username tentado, útil para detectar
    # tentativas repetidas sem expor nenhum segredo.
    registrar(
        acao="login.falha",
        request=request,
        detalhes={"username": credentials.get("username", "")},
    )
