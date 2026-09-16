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

`apps/auditoria/admin.py` cobre a INTERFACE; o manager do modelo cobre
`QuerySet.update()`/`delete()`/`bulk_update()`, que não emitem signals; e
este módulo cobre os caminhos de instância. Os dois níveis precisam falhar
o mais cedo possível para que `registrar()` na camada de serviço (BL-14)
também não seja capaz de reescrever o histórico.

Quem NÃO é bloqueado:
- `RegistroAuditoria.objects.create(...)` continua funcionando — novos
  registros são o que a trilha é feita de. O `pre_save` distingue
  INSERT de UPDATE por `_state.adding`, e só bloqueia o segundo.
- A leitura (`filter`, `get`, `count`, listagens) segue igual.

BL-244 (DL-024): trilha para o painel administrativo.

Medido pelo auditor: nenhum `apps/*/admin.py` chama `registrar()`.
Alterar `Empresa`, `Conta`, `Estabelecimento`, `HistoricoRegimeTributario`,
`Escritorio` ou `VinculoUsuarioEscritorio` pelo admin saía sem rastro na
trilha do produto (só `LogEntry` do Django, que é log de framework).

Esta seção registra signals `pre_save`, `post_save` e `pre_delete` para
a lista EXPLICITA de modelos. A detecção do "caminho admin" usa
`apps.core.current_request` — preenchida por
`apps.core.middleware.CurrentRequestMiddleware` — e o teste de
`request.path.startswith("/admin/")`. Se a request não é do admin (API,
teste, management command), os handlers caem fora silenciosamente — as
views continuam responsáveis pelo seu próprio `registrar()` (BL-14), e
a BL-244 não duplica trilha.

Atomicidade: os signals rodam DENTRO da transação aberta pelo admin
(`ModelAdmin.save_model` é chamado dentro de uma transação por padrão).
Se `registrar()` falhar, o `pre_save` BL-16 do `RegistroAuditoria` (que
roda ANTES do nosso `pre_save` na ordem em que foi registrado)
bloqueia o update do log primeiro, ou — no caso do `post_save` — o
erro propaga e a transação reverte junto. O `pre_save` aqui só lê
(`Empresa.objects.get(pk=...)`) para o snapshot; é seguro.
"""

from django.core.exceptions import PermissionDenied
from django.db.models.signals import post_save, pre_delete, pre_save
from django.dispatch import receiver

from apps.auditoria.models import MENSAGEM_IMUTABILIDADE, RegistroAuditoria
from apps.auditoria.services import registrar
from apps.contabilidade.models import Conta
from apps.core.current_request import get_current_request
from apps.empresas.models import Empresa, Estabelecimento, HistoricoRegimeTributario
from apps.tenancy.models import Escritorio, VinculoUsuarioEscritorio

# --- BL-16 ----------------------------------------------------------------

MENSAGEM_DELETE = (
    f"{MENSAGEM_IMUTABILIDADE}: "
    "registros de auditoria são imutáveis — "
    "delete (incluindo o do QuerySet em massa) é proibido. "
    "Se a trilha precisa ser corrigida, registre um novo evento, "
    "não reescreva o histórico."
)
MENSAGEM_UPDATE = (
    f"{MENSAGEM_IMUTABILIDADE}: "
    "registros de auditoria são imutáveis — "
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


# --- BL-244 ---------------------------------------------------------------

# Lista EXPLICITA de modelos cobertos pela trilha do admin. Adicionar
# aqui um modelo novo é uma decisão consciente — não acontece por
# acaso. O `LogEntry` do Django NÃO está aqui (tem trilha própria do
# framework). O `Usuario` está coberto em `apps.accounts.signals.py`
# (login/logout) e não pelo admin — uma alteração de superuser via
# admin pode ficar fora por ora; é item de DL futura, fora do escopo
# da DL-024.
MODELOS_DA_TRILHA_DO_ADMIN = (
    Empresa,
    Conta,
    Estabelecimento,
    HistoricoRegimeTributario,
    Escritorio,
    VinculoUsuarioEscritorio,
)


def _vem_do_admin(request):
    """Detecta se a operação em curso vem do painel administrativo.

    Heurística: `request.path.startswith("/admin/")`. Simples, estável,
    não depende do `resolver_match` (que pode não estar disponível no
    ponto em que o middleware rodou) e cobre tanto o admin do Django
    quanto qualquer customização que mantenha o prefixo `/admin/`.
    """
    if request is None:
        return False
    return request.path.startswith("/admin/")


def _snapshot_dos_campos(instance):
    """Devolve um dict simples com os campos do modelo para uso na
    trilha. Não é ISO 8601, não é serialização completa — é só o que
    o usuário precisa para entender o que mudou."""
    import json

    from django.core.serializers.json import DjangoJSONEncoder

    campos = {f.name: f.value_from_object(instance) for f in instance._meta.fields}
    return json.loads(json.dumps(campos, cls=DjangoJSONEncoder))


@receiver(pre_save)
def _admin_pre_save_snapshot(sender, instance, **kwargs):
    """Tira snapshot dos valores ANTES do save.

    Roda para qualquer `pre_save` de qualquer modelo. Só atua quando:
    - `sender` está na lista `MODELOS_DA_TRILHA_DO_ADMIN`, E
    - a operação NÃO é INSERT (`_state.adding == False`), E
    - a request corrente vem do admin.

    Nos outros casos, sai sem fazer nada (registros via API continuam
    sendo responsabilidade da view). O snapshot fica em
    `instance._valores_anteriores` e é lido por `_admin_post_save` e
    `_admin_pre_delete`.
    """
    if sender not in MODELOS_DA_TRILHA_DO_ADMIN:
        return
    if instance._state.adding:
        return  # INSERT: nada a comparar
    if not _vem_do_admin(get_current_request()):
        return  # não-admin: a view já registra por conta própria
    try:
        anterior = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        instance._valores_anteriores = {}
        return
    instance._valores_anteriores = _snapshot_dos_campos(anterior)


@receiver(post_save)
def _admin_post_save_registra(sender, instance, created, **kwargs):
    """Registra a trilha após save feito pelo admin.

    Só atua quando o `pre_save` deixou `_valores_anteriores` na
    instance — ou seja, é UPDATE via admin. INSERT via admin também
    é coberto, com diff vazio e `detalhes` mínimo (sem valores
    anteriores).
    """
    if sender not in MODELOS_DA_TRILHA_DO_ADMIN:
        return
    request = get_current_request()
    if not _vem_do_admin(request):
        return
    valores_anteriores = getattr(instance, "_valores_anteriores", {}) or {}
    diff_anterior = {}
    diff_novo = {}
    if not created and valores_anteriores:
        valores_novos = _snapshot_dos_campos(instance)
        for campo in valores_anteriores:
            if campo in valores_novos and valores_anteriores[campo] != valores_novos[campo]:
                diff_anterior[campo] = valores_anteriores[campo]
                diff_novo[campo] = valores_novos[campo]
    if created or diff_anterior:
        # `model._meta.label_lower` ("empresa.empresa") dá a origem
        # estável do sinal. A acao distingue INSERT/UPDATE/DELETE.
        sufixo = "admin_criado" if created else "admin_atualizado"
        detalhes = {}
        if diff_anterior:
            detalhes["valores_anteriores"] = diff_anterior
            detalhes["valores_novos"] = diff_novo
        registrar(
            acao=f"{sender._meta.label_lower}.{sufixo}",
            objeto=instance,
            request=request,
            detalhes=detalhes,
        )


@receiver(pre_delete)
def _admin_pre_delete_registra(sender, instance, **kwargs):
    """Registra a trilha ANTES do delete feito pelo admin.

    O snapshot precisa ter sido tirado antes do save — então lemos o
    `_valores_anteriores` deixado por `_admin_pre_save_snapshot` (que
    rodou no save anterior). Se nunca houve save anterior (registro
    criado direto e já apagado sem passar pelo admin), o dict está
    vazio e a trilha registra `admin_excluido` com `detalhes`
    mínimos — ainda é melhor que nada.
    """
    if sender not in MODELOS_DA_TRILHA_DO_ADMIN:
        return
    request = get_current_request()
    if not _vem_do_admin(request):
        return
    valores_anteriores = getattr(instance, "_valores_anteriores", None)
    if valores_anteriores is None:
        valores_anteriores = _snapshot_dos_campos(instance)
    registrar(
        acao=f"{sender._meta.label_lower}.admin_excluido",
        objeto=instance,
        request=request,
        detalhes={"valores_anteriores": valores_anteriores},
    )
