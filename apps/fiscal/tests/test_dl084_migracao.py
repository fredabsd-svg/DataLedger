"""DL-084: migração 0015 aplicada, revertida e reaplicada pelo `migrate` do Django, com dados.

- Ida: a carga de Palmas/TO entra com lei e data da leitura.
- Volta com dado do contador (competência, parâmetro ou encerramento): RECUSA, e nada muda no banco.
- Volta sem dado do contador: passa, e a reaplicação recria a carga.

Usa `transaction=True`: a reversão precisa rodar fora de transação de teste. Cada teste termina no
head, como estava.
"""

from datetime import date

import pytest
from django.core.management import call_command
from django.db import connection

from apps.empresas.models import Empresa
from apps.fiscal.models import FeriadoLocal, ParametrosPresumidoEmpresa

ULTIMA_ANTES = "0014_dl082_pre_das_comercio"
ULTIMA = "0015_dl084_rotina_do_presumido"


def _tabelas_existem():
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('fiscal_feriadolocal') IS NOT NULL")
        return cursor.fetchone()[0]


@pytest.mark.django_db(transaction=True)
def test_ida_volta_e_ida_com_a_carga_de_palmas():
    call_command("migrate", "fiscal", ULTIMA_ANTES, verbosity=0)
    assert _tabelas_existem() is False
    call_command("migrate", "fiscal", ULTIMA, verbosity=0)
    assert FeriadoLocal.objects.filter(uf="TO", municipio="PALMAS").count() == 5
    call_command("migrate", "fiscal", ULTIMA_ANTES, verbosity=0)
    assert _tabelas_existem() is False
    call_command("migrate", "fiscal", ULTIMA, verbosity=0)
    assert FeriadoLocal.objects.filter(uf="TO").count() == 8
    assert all(
        f.fundamento and f.data_leitura == date(2026, 10, 9) for f in FeriadoLocal.objects.all()
    )


@pytest.mark.django_db(transaction=True)
def test_volta_recusa_com_parametro_do_contador_e_nao_altera_nada(escritorio_a):
    from apps.tenancy.models import Papel

    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Cliente migração Ltda", cnpj="77888999000170"
    )
    usuario = _usuario_gestor(escritorio_a, "gestor-migracao-parametro-dl084", Papel.GESTOR)
    # O teste transacional limpa o banco ao terminar: compara antes e depois, sem supor a carga.
    feriados_antes = FeriadoLocal.objects.count()
    ParametrosPresumidoEmpresa.objects.create(
        empresa=empresa, forma_recolhimento="quota_unica", atualizado_por=usuario
    )
    with pytest.raises(RuntimeError, match="Reversão da DL-084 recusada"):
        call_command("migrate", "fiscal", ULTIMA_ANTES, verbosity=0)
    # Recusou: a tabela, a carga e o parâmetro continuam como estavam.
    assert _tabelas_existem() is True
    assert ParametrosPresumidoEmpresa.objects.filter(empresa=empresa).exists()
    assert FeriadoLocal.objects.count() == feriados_antes
    ParametrosPresumidoEmpresa.objects.filter(empresa=empresa).delete()


def _usuario_gestor(escritorio, username, papel):
    from django.contrib.auth import get_user_model

    from apps.tenancy.models import VinculoUsuarioEscritorio

    usuario = get_user_model().objects.create_user(
        username=username,
        email=f"{username}@escritorio-fiscal-teste.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario
