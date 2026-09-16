"""DL-023, critério 13 (achado do inventário de `24f6bbc`, medido pelo
`auxiliar-pesquisa` na abertura da etapa).

O defeito: `RegistroAuditoriaAdmin.has_add_permission` e
`has_change_permission` já devolviam `False`, e todos os campos já eram
`readonly` — mas `has_delete_permission` NÃO estava sobrescrito, então a
exclusão ficava sujeita só à permissão de modelo padrão do Django
(`auditoria.delete_registroauditoria`). Qualquer usuário com essa
permissão podia apagar registro de auditoria pelo admin, individualmente
OU pela ação em lote da listagem — sem nenhuma checagem própria.

A trilha de auditoria é o que resta quando todo o resto falha
(AGENTS.md, seção 11: "trilha de auditoria protegida"). Os dois testes
abaixo provam a exclusão INDIVIDUAL e a exclusão EM LOTE, cada uma por
requisição autenticada — `has_delete_permission` devolvendo `False` só
prova alguma coisa se alguém tentar de verdade.
"""

import pytest
from django.contrib.auth import get_user_model

from apps.auditoria.models import RegistroAuditoria

SENHA = "senha-forte-123"
pytestmark = pytest.mark.django_db


@pytest.fixture
def registro():
    return RegistroAuditoria.objects.create(
        acao="teste.dl023",
        objeto_tipo="Teste",
        objeto_id="1",
        detalhes={"origem": "DL-023"},
    )


@pytest.fixture
def superusuario():
    # `is_superuser=True` tem `has_delete_permission` do Django devolvendo
    # `True` por padrão para QUALQUER modelo — é exatamente o perfil que
    # provaria a lacuna antiga (a permissão de modelo bastava) e é quem
    # precisa continuar recebendo `False` depois da correção, porque
    # `RegistroAuditoriaAdmin.has_delete_permission` está sobrescrito e
    # ignora a permissão padrão.
    return get_user_model().objects.create_superuser(
        username="admin-dl023-auditoria",
        email="admin-dl023-auditoria@escritorio.com.br",
        password=SENHA,
    )


def _login(client, superusuario):
    assert client.login(username="admin-dl023-auditoria", password=SENHA)


def test_exclusao_individual_pelo_admin_e_recusada(client, registro, superusuario):
    _login(client, superusuario)

    resposta = client.post(
        f"/admin/auditoria/registroauditoria/{registro.pk}/delete/", {"post": "yes"}
    )

    assert resposta.status_code == 403, (resposta.status_code, resposta.content)
    assert RegistroAuditoria.objects.filter(pk=registro.pk).exists()


def test_exclusao_em_lote_pelo_admin_e_recusada(client, registro, superusuario):
    _login(client, superusuario)

    resposta = client.post(
        "/admin/auditoria/registroauditoria/",
        {
            "action": "delete_selected",
            "_selected_action": [str(registro.pk)],
        },
    )

    # A ação em lote nem chega a oferecer a confirmação de exclusão — sem
    # `has_delete_permission`, "delete_selected" não é uma ação disponível
    # para este ModelAdmin; a listagem responde normalmente (200), sem
    # apagar nada.
    assert resposta.status_code in (200, 403), (resposta.status_code, resposta.content)
    assert RegistroAuditoria.objects.filter(pk=registro.pk).exists()


def test_has_delete_permission_devolve_false(registro, superusuario):
    """Unidade direta do método (critério 13, primeira metade literal):
    `has_delete_permission` devolve `False` em `RegistroAuditoriaAdmin` —
    inclusive para superusuário, que teria `True` sem a sobrescrita."""
    from django.contrib import admin as django_admin

    from apps.auditoria.admin import RegistroAuditoriaAdmin

    modeladmin = RegistroAuditoriaAdmin(RegistroAuditoria, django_admin.site)

    assert modeladmin.has_delete_permission(None, obj=registro) is False
    assert modeladmin.has_delete_permission(None, obj=None) is False
