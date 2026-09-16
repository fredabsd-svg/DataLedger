"""BL-16 (DL-024): imutabilidade do `RegistroAuditoria` contra
`update()`/`delete()` em massa.

Medido pelo auditor: o caminho individual (admin) já estava fechado pela
DL-023 — `RegistroAuditoriaAdmin.has_delete_permission` e
`has_change_permission` devolvem `False`. Mas o `QuerySet` do manager
continuava aberto:

- `RegistroAuditoria.objects.all().delete()` retornava `(N,)` e esvaziava
  a tabela em silêncio.
- `RegistroAuditoria.objects.filter(acao='login.sucesso').update(acao='foo')`
  retornava `3` e reescrevia o histórico sem deixar rastro.

`apps/auditoria/admin.py` cobre a INTERFACE; este módulo cobre o MODELO.
A defesa mora no signal handler (Django não tem `delete_enabled`/`update_enabled`
nativo no `Meta`), e os dois caminhos (delete em massa, update em massa)
precisam falhar o mais cedo possível para que `registrar()` na camada
de serviço (BL-14) também não seja capaz de reescrever o histórico.

Quem NÃO é bloqueado:
- `RegistroAuditoria.objects.create(...)` continua funcionando — novos
  registros são o que a trilha é feita de. O `pre_save` distingue
  INSERT de UPDATE por `_state.adding`, e só bloqueia o segundo.
- A leitura (`filter`, `get`, `count`, listagens) segue igual.
"""

from django.core.exceptions import PermissionDenied
from django.db.models.signals import pre_delete, pre_save
from django.dispatch import receiver

from apps.auditoria.models import RegistroAuditoria

MENSAGEM_DELETE = (
    "RegistroAuditoria: registros de auditoria são imutáveis — "
    "delete (incluindo o do QuerySet em massa) é proibido. "
    "Se a trilha precisa ser corrigida, registre um novo evento, "
    "não reescreva o histórico."
)
MENSAGEM_UPDATE = (
    "RegistroAuditoria: registros de auditoria são imutáveis — "
    "update (incluindo o do QuerySet em massa) é proibido. "
    "Se a trilha precisa ser corrigida, registre um novo evento, "
    "não reescreva o histórico."
)


@receiver(pre_delete, sender=RegistroAuditoria)
def _registro_auditoria_imutavel_para_delete(sender, instance, **kwargs):
    """Bloqueia `instance.delete()` e `QuerySet.delete()`.

    Disparado pelo signal `pre_delete` do Django, que cobre tanto a
    exclusão individual (`instance.delete()`) quanto a do manager
    (`QuerySet.delete()`) — qualquer `delete()` que chegue ao ORM
    passa por aqui antes de o ORM emitir o SQL.
    """
    raise PermissionDenied(MENSAGEM_DELETE)


@receiver(pre_save, sender=RegistroAuditoria)
def _registro_auditoria_imutavel_para_update(sender, instance, **kwargs):
    """Bloqueia o caminho de UPDATE; deixa o de INSERT passar.

    `pre_save` é disparado tanto para `create()` quanto para `save()` em
    instância já persistida. O atributo Django `_state.adding` distingue:
    é `True` enquanto a instância nunca foi gravada (INSERT), e vira
    `False` depois do primeiro save. Bloquear só quando `adding` é `False`
    é o que mantém `create()` (a única escrita legítima) funcionando.
    """
    if not instance._state.adding:
        raise PermissionDenied(MENSAGEM_UPDATE)
