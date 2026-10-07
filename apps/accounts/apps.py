from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    label = "accounts"

    def ready(self):
        from django.contrib import admin

        from apps.accounts import signals  # noqa: F401
        from apps.accounts.forms import AdminLoginForm

        # DL-068: o `/admin/login/` usa o formulário com limite de tentativas
        # (DL-056). Fica aqui, e não em `admin.py`, de propósito: o controle de
        # segurança não pode depender de o autodiscover do admin importar o
        # `admin.py` deste app, nem da ordem dos `ready()`. O import é tardio
        # porque `forms` importa modelos, que só existem depois do registro de
        # apps. O `AdminSite.login` lê `login_form` a cada requisição, então
        # basta estar definido antes da primeira; não há risco de ordem.
        admin.site.login_form = AdminLoginForm
