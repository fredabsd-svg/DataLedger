from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import models

from apps.tenancy.models import Escritorio

MENSAGEM_IMUTABILIDADE = "registro de auditoria é imutável"
_HINT_LIMPEZA_REFERENCIAL = "_auditoria_limpeza_referencial"


def _set_null_preservando_trilha(collector, field, sub_objs, using):
    """Permite apenas o `SET_NULL` interno que preserva a trilha.

    A exclusão de ESCRITÓRIO deve manter o evento, anulando só sua FK. (A de
    usuário deixou de existir: pela RC-144 — DL-052, decisão do Fred em
    30/09/2026 — usuário se desativa, não se apaga, e `RegistroAuditoria.
    usuario` é PROTECT; este tratamento serve hoje só a `escritorio`.) O coletor de exclusão do Django executa essa ação com
    `QuerySet.update()`, que a proteção de imutabilidade bloqueia por padrão;
    o marcador privado diferencia essa limpeza referencial inevitável de
    uma tentativa de reescrever a auditoria.
    """
    sub_objs._add_hints(**{_HINT_LIMPEZA_REFERENCIAL: True})
    collector.add_field_update(field, None, sub_objs)


class RegistroAuditoriaQuerySet(models.QuerySet):
    """QuerySet que fecha mutações em massa da trilha.

    `QuerySet.update()` e `bulk_update()` não chamam `Model.save()` nem
    emitem `pre_save`; por isso o signal de `apps.auditoria.signals` não
    alcança esses caminhos. A defesa precisa morar também no manager do
    próprio modelo, para que uma mutação em massa não consiga reescrever ou
    apagar o histórico fora da interface.
    """

    def update(self, **kwargs):
        if self._hints.get(_HINT_LIMPEZA_REFERENCIAL):
            return super().update(**kwargs)
        raise PermissionDenied(MENSAGEM_IMUTABILIDADE)

    def bulk_update(self, objs, fields, batch_size=None):
        raise PermissionDenied(MENSAGEM_IMUTABILIDADE)

    def delete(self):
        raise PermissionDenied(MENSAGEM_IMUTABILIDADE)


class RegistroAuditoria(models.Model):
    """Registro de uma ação relevante: quem fez, em qual escritório, o quê.

    Nunca gravar senha, token, documento pessoal completo ou qualquer outro
    dado sensível em `detalhes` — apenas identificadores e um resumo não
    sensível da ação, conforme AGENTS.md, seção 11. `escritorio` usa SET_NULL
    (via `_set_null_preservando_trilha`) para que a exclusão de um escritório
    não apague o histórico. `usuario` é PROTECT desde a RC-144 (DL-052): o
    usuário se desativa, não se apaga, e apagar um usuário que tem trilha é
    recusado (`ProtectedError`) em vez de apagar a autoria do evento.
    """

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="usuário",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="registros_auditoria",
    )
    escritorio = models.ForeignKey(
        Escritorio,
        verbose_name="escritório",
        null=True,
        blank=True,
        on_delete=_set_null_preservando_trilha,
        related_name="registros_auditoria",
    )
    acao = models.CharField("ação", max_length=100)
    objeto_tipo = models.CharField("tipo do objeto", max_length=100, blank=True)
    objeto_id = models.CharField("ID do objeto", max_length=50, blank=True)
    detalhes = models.JSONField("detalhes", default=dict, blank=True)
    endereco_ip = models.GenericIPAddressField("endereço IP", null=True, blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    objects = models.Manager.from_queryset(RegistroAuditoriaQuerySet)()

    class Meta:
        verbose_name = "registro de auditoria"
        verbose_name_plural = "registros de auditoria"
        ordering = ["-criado_em"]

    def __str__(self):
        return f"{self.acao} — {self.usuario} — {self.criado_em:%Y-%m-%d %H:%M}"
