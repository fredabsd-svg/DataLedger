"""RC-144 / DL-052 (decisão do Fred, 30/09/2026): usuário se desativa, não se apaga.

`RegistroAuditoria.usuario` passa a PROTECT: apagar um usuário que tem trilha é
recusado, e o evento mantém o autor. `RegistroAuditoria.escritorio` NÃO muda —
apagar um escritório continua anulando só essa FK (a imutabilidade da trilha
segue coberta em `test_dl024_imutabilidade_auditoria.py`). Dados sintéticos.
"""

import pytest
from django.contrib.auth import get_user_model
from django.db.models import ProtectedError

from apps.auditoria.models import RegistroAuditoria
from apps.auditoria.services import registrar
from apps.tenancy.models import Escritorio

pytestmark = pytest.mark.django_db


def test_apagar_usuario_com_trilha_e_recusado_e_o_evento_mantem_o_autor():
    usuario = get_user_model().objects.create_user(
        username="autor-trilha-052", email="autor-trilha-052@escritorio.com.br"
    )
    escritorio = Escritorio.objects.create(nome="Escritório trilha 052", cnpj="54545454000154")
    registro = registrar(acao="teste.dl052", escritorio=escritorio, usuario=usuario)

    with pytest.raises(ProtectedError):
        usuario.delete()

    assert get_user_model().objects.filter(pk=usuario.pk).exists()
    registro.refresh_from_db()
    assert registro.usuario_id == usuario.pk


def test_apagar_usuario_sem_trilha_continua_possivel():
    usuario = get_user_model().objects.create_user(
        username="sem-trilha-052", email="sem-trilha-052@escritorio.com.br"
    )

    usuario.delete()

    assert not get_user_model().objects.filter(username="sem-trilha-052").exists()


def test_apagar_escritorio_continua_anulando_so_a_fk_do_escritorio():
    usuario = get_user_model().objects.create_user(
        username="autor-esc-052", email="autor-esc-052@escritorio.com.br"
    )
    escritorio = Escritorio.objects.create(nome="Escritório some 052", cnpj="54545454000235")
    registro = registrar(acao="teste.dl052.escritorio", escritorio=escritorio, usuario=usuario)

    escritorio.delete()

    registro.refresh_from_db()
    assert registro.escritorio_id is None
    assert registro.usuario_id == usuario.pk
    assert RegistroAuditoria.objects.filter(pk=registro.pk).exists()
