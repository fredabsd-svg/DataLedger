from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from apps.accounts.limite_tentativas import resumo_do_usuario
from apps.auditoria.services import registrar


@receiver(user_logged_in)
def registrar_login_sucesso(sender, request, user, **kwargs):
    registrar(acao="login.sucesso", usuario=user, request=request)


@receiver(user_logged_out)
def registrar_logout(sender, request, user, **kwargs):
    registrar(acao="logout", usuario=user, request=request)


@receiver(user_login_failed)
def registrar_login_falha(sender, credentials, request=None, **kwargs):
    # Nunca gravar a senha. DL-058/B3: o campo "usuário" também não vai
    # cru para a trilha quando não corresponde a uma conta — quem digita a
    # senha no campo errado a colocaria na trilha de auditoria, em claro.
    # Conta existente: grava o nome (já é dado da própria conta, útil para
    # detectar tentativas repetidas contra ela). Conta inexistente: grava
    # só o resumo HMAC (`resumo_do_usuario`, o mesmo do limitador da DL-056),
    # que ainda permite agrupar a mesma tentativa.
    digitado = str(credentials.get("username", "") or "")
    conta_existe = (
        bool(digitado)
        and get_user_model()._default_manager.filter(username__iexact=digitado).exists()
    )
    if conta_existe:
        detalhes = {"username": digitado}
    else:
        detalhes = {"username_hmac": resumo_do_usuario(digitado)}
    registrar(acao="login.falha", request=request, detalhes=detalhes)
