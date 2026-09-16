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
        from apps.auditoria import signals  # noqa: F401
