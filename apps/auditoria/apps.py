from django.apps import AppConfig


class AuditoriaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.auditoria"
    label = "auditoria"

    def ready(self):
        # BL-16 (DL-024): registra os signals que tornam o
        # `RegistroAuditoria` imutável contra `delete()` e `update()`
        # em massa. Importar dentro de `ready()` é a forma Django de
        # evitar ciclos e de garantir que o decorator `@receiver` receba
        # o sender depois que o app está carregado.
        #
        # DL-068 (BL-577): `checks` entra no mesmo import porque importar o
        # módulo é o que REGISTRA a verificação `auditoria.W001` (decorator
        # `@register`), pelo mesmo motivo acima.
        from apps.auditoria import checks, signals  # noqa: F401
