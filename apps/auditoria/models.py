from django.conf import settings
from django.db import models

from apps.tenancy.models import Escritorio


class RegistroAuditoria(models.Model):
    """Registro de uma ação relevante: quem fez, em qual escritório, o quê.

    Nunca gravar senha, token, documento pessoal completo ou qualquer outro
    dado sensível em `detalhes` — apenas identificadores e um resumo não
    sensível da ação, conforme AGENTS.md, seção 11. `usuario` e
    `escritorio` usam SET_NULL para que a exclusão de um usuário ou
    escritório não apague o histórico de auditoria.
    """

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="usuário",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="registros_auditoria",
    )
    escritorio = models.ForeignKey(
        Escritorio,
        verbose_name="escritório",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="registros_auditoria",
    )
    acao = models.CharField("ação", max_length=100)
    objeto_tipo = models.CharField("tipo do objeto", max_length=100, blank=True)
    objeto_id = models.CharField("ID do objeto", max_length=50, blank=True)
    detalhes = models.JSONField("detalhes", default=dict, blank=True)
    endereco_ip = models.GenericIPAddressField("endereço IP", null=True, blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "registro de auditoria"
        verbose_name_plural = "registros de auditoria"
        ordering = ["-criado_em"]

    def __str__(self):
        return f"{self.acao} — {self.usuario} — {self.criado_em:%Y-%m-%d %H:%M}"
