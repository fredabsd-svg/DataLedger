"""BL-16 (DL-024): imutabilidade do `RegistroAuditoria` contra
`update()` e `delete()` em massa.

Medido pelo auditor: a defesa individual do admin foi acrescentada na
DL-023 (`RegistroAuditoriaAdmin.has_delete_permission` e
`has_change_permission` devolvem `False`), mas o `QuerySet` do manager
continuava aberto:

- `RegistroAuditoria.objects.all().delete()` retornava `(N,)` e esvaziava
  a tabela em silêncio.
- `RegistroAuditoria.objects.filter(...).update(...)` retornava a
  contagem e reescrevia o histórico sem deixar rastro.

A defesa combina o manager de `RegistroAuditoria` com
`apps/auditoria/signals.py`: o `QuerySet` bloqueia `update()`,
`bulk_update()` e `delete()` em massa, enquanto `pre_delete` e `pre_save`
protegem os caminhos de instância. O `create()` continua funcionando —
novos registros são o que a trilha é feita de.

Testes:

1. **Estático** (`test_*`): lê o fonte via `inspect.getsource` e confirma
   que os signals estão registrados, ancorados no sender certo, e
   levantam `PermissionDenied`. Roda sem banco.

2. **Runtime** (`@pytest.mark.django_db(transaction=True)`): usa o
   ORM de verdade e prova que cada caminho (`instance.delete()`,
   `QuerySet.delete()`, `QuerySet.update()`, `instance.save()` em
   registro já persistido) levanta `PermissionDenied`. A CI é quem
   roda — `pytest-django` exige PostgreSQL.
"""

import inspect

import pytest

# Sem `pytestmark = pytest.mark.django_db` no nível do módulo: os testes
# ESTÁTICOS não precisam de banco, e a marca global forçaria a
# inicialização do Postgres em todos eles. Os testes RUNTIME marcam-se
# individualmente.


# -----------------------------------------------------------------------
# 1. Fonte estático — signals existem e disparam `PermissionDenied`
# -----------------------------------------------------------------------


def test_signals_de_imutabilidade_existem_e_estao_anexados_ao_sender():
    """`apps/auditoria/signals.py` define dois receivers:
    `_registro_auditoria_imutavel_para_delete` e
    `_registro_auditoria_imutavel_para_update`, e ambos devem usar o
    decorator `@receiver(pre_..., sender=RegistroAuditoria)`.

    Sem isso, a defesa não é aplicada. O `apps.py` precisa importar o
    módulo de signals em `ready()` para que o decorator rode no startup.
    """
    from apps.auditoria import signals

    src = inspect.getsource(signals)
    assert "_registro_auditoria_imutavel_para_delete" in src, (
        "BL-16: handler de delete imutável não encontrado em signals.py"
    )
    assert "_registro_auditoria_imutavel_para_update" in src, (
        "BL-16: handler de update imutável não encontrado em signals.py"
    )
    assert "@receiver(pre_delete" in src, (
        "BL-16: handler de delete precisa estar ancorado em "
        "`@receiver(pre_delete, sender=RegistroAuditoria)`"
    )
    assert "@receiver(pre_save" in src, (
        "BL-16: handler de update precisa estar ancorado em "
        "`@receiver(pre_save, sender=RegistroAuditoria)`"
    )
    assert "sender=RegistroAuditoria" in src, (
        "BL-16: os signals precisam do `sender=RegistroAuditoria` "
        "para não disparar em outros modelos"
    )


def test_handler_de_delete_levanta_permission_denied():
    from django.core.exceptions import PermissionDenied

    from apps.auditoria import signals
    from apps.auditoria.models import RegistroAuditoria

    # O handler de delete precisa levantar PermissionDenied. O `instance`
    # é criado só para satisfazer a assinatura; o que importa é o raise.
    with pytest.raises(PermissionDenied):
        signals._registro_auditoria_imutavel_para_delete(
            sender=RegistroAuditoria, instance=RegistroAuditoria()
        )


def test_handler_de_update_levanta_permission_denied_quando_nao_eh_adding():
    from django.core.exceptions import PermissionDenied

    from apps.auditoria import signals

    # Instância com `_state.adding = False` simula UPDATE. O handler
    # precisa levantar.
    class FakeInst:
        _state = type("_state", (), {"adding": False})()

    with pytest.raises(PermissionDenied):
        signals._registro_auditoria_imutavel_para_update(sender=object(), instance=FakeInst())


def test_handler_de_update_nao_levanta_quando_eh_adding():
    """`create()` (INSERT) é o único caminho de escrita legítimo —
    o handler NÃO pode bloquear."""
    from apps.auditoria import signals

    class FakeInst:
        _state = type("_state", (), {"adding": True})()

    # Não deve levantar — é INSERT.
    signals._registro_auditoria_imutavel_para_update(sender=object(), instance=FakeInst())


def test_apps_auditoria_importa_signals_em_ready():
    """`apps/auditoria/apps.py` precisa importar `signals` em `ready()`
    para que os `@receiver` rodem no startup. Sem isso, o handler existe
    no Python mas nunca é conectado ao signal do ORM."""
    from apps.auditoria.apps import AuditoriaConfig

    src = inspect.getsource(AuditoriaConfig.ready)
    assert "signals" in src, (
        "BL-16: `apps/auditoria/apps.py:AuditoriaConfig.ready()` precisa "
        "importar `apps.auditoria.signals` para conectar os receivers."
    )


def test_queryset_de_registroauditoria_bloqueia_mutacoes_em_massa():
    """O ORM em massa não emite signals; o manager precisa fechar esses
    métodos diretamente, inclusive `bulk_update()` fora do aceite mínimo."""
    from django.db import models

    from apps.auditoria.models import RegistroAuditoriaQuerySet

    assert RegistroAuditoriaQuerySet.update is not models.QuerySet.update
    assert RegistroAuditoriaQuerySet.bulk_update is not models.QuerySet.bulk_update
    assert RegistroAuditoriaQuerySet.delete is not models.QuerySet.delete


def test_manager_recusa_update_e_delete_antes_de_consultar_o_banco():
    """A defesa do manager é exercitável sem conexão: nenhum SQL deve ser
    necessário para recusar as duas mutações em massa."""
    from django.core.exceptions import PermissionDenied

    from apps.auditoria.models import RegistroAuditoria

    with pytest.raises(PermissionDenied, match="registro de auditoria é imutável"):
        RegistroAuditoria.objects.all().update(acao="fraude")
    with pytest.raises(PermissionDenied, match="registro de auditoria é imutável"):
        RegistroAuditoria.objects.all().delete()


# -----------------------------------------------------------------------
# 2. Runtime — paths bloqueados pelo ORM de verdade (CI only)
# -----------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_registroauditoria_objects_all_delete_e_bloqueado():
    from django.core.exceptions import PermissionDenied

    from apps.auditoria.models import RegistroAuditoria

    with pytest.raises(PermissionDenied):
        RegistroAuditoria.objects.all().delete()


@pytest.mark.django_db(transaction=True)
def test_registroauditoria_queryset_filtered_delete_e_bloqueado():
    from django.contrib.auth import get_user_model
    from django.core.exceptions import PermissionDenied

    from apps.auditoria.models import RegistroAuditoria
    from apps.auditoria.services import registrar
    from apps.tenancy.models import Escritorio

    escritorio = Escritorio.objects.create(nome="E BL-16", cnpj="11111111000111")
    usuario = get_user_model().objects.create_user(username="u-bl16", password="senha-forte-123")
    registrar(acao="login.teste", escritorio=escritorio, usuario=usuario)

    with pytest.raises(PermissionDenied):
        RegistroAuditoria.objects.filter(acao="login.teste").delete()


@pytest.mark.django_db(transaction=True)
def test_registroauditoria_queryset_update_e_bloqueado():
    from django.contrib.auth import get_user_model
    from django.core.exceptions import PermissionDenied

    from apps.auditoria.models import RegistroAuditoria
    from apps.auditoria.services import registrar
    from apps.tenancy.models import Escritorio

    escritorio = Escritorio.objects.create(nome="E BL-16b", cnpj="22222222000122")
    usuario = get_user_model().objects.create_user(username="u-bl16b", password="senha-forte-123")
    registrar(acao="login.teste", escritorio=escritorio, usuario=usuario)

    with pytest.raises(PermissionDenied):
        RegistroAuditoria.objects.filter(acao="login.teste").update(acao="foo")


@pytest.mark.django_db(transaction=True)
def test_registroauditoria_instance_delete_e_bloqueado():
    from django.contrib.auth import get_user_model
    from django.core.exceptions import PermissionDenied

    from apps.auditoria.services import registrar
    from apps.tenancy.models import Escritorio

    escritorio = Escritorio.objects.create(nome="E BL-16c", cnpj="33333333000133")
    usuario = get_user_model().objects.create_user(username="u-bl16c", password="senha-forte-123")
    reg = registrar(acao="login.teste", escritorio=escritorio, usuario=usuario)

    with pytest.raises(PermissionDenied):
        reg.delete()


@pytest.mark.django_db(transaction=True)
def test_registroauditoria_save_em_instancia_persistida_e_bloqueado():
    """`instance.save()` em registro JÁ gravado é equivalente a UPDATE,
    e o handler de `pre_save` deve bloquear quando `_state.adding` é False."""
    from django.contrib.auth import get_user_model
    from django.core.exceptions import PermissionDenied

    from apps.auditoria.services import registrar
    from apps.tenancy.models import Escritorio

    escritorio = Escritorio.objects.create(nome="E BL-16d", cnpj="44444444000144")
    usuario = get_user_model().objects.create_user(username="u-bl16d", password="senha-forte-123")
    reg = registrar(acao="login.teste", escritorio=escritorio, usuario=usuario)
    # `reg.save()` em instância já persistida = UPDATE, deve falhar.
    reg.acao = "foo"
    with pytest.raises(PermissionDenied):
        reg.save()


@pytest.mark.django_db(transaction=True)
def test_set_null_de_referencias_preserva_o_evento_ao_excluir_escritorio():
    """A limpeza referencial de `SET_NULL` é a única atualização interna
    permitida: o vínculo some, mas o evento continua no histórico."""
    from django.contrib.auth import get_user_model

    from apps.auditoria.services import registrar
    from apps.tenancy.models import Escritorio

    escritorio = Escritorio.objects.create(nome="E BL-16 SET NULL", cnpj="16161616000116")
    usuario = get_user_model().objects.create_user(username="u-bl16-set-null")
    registro = registrar(acao="login.teste", escritorio=escritorio, usuario=usuario)

    escritorio.delete()

    registro.refresh_from_db()
    assert registro.escritorio_id is None
